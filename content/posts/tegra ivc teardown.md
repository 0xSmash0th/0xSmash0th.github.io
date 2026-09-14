+++
title = 'Tegra IVC Teardown'
date = 2026-09-02T00:00:00Z
draft = true
description = "Is Tegra's Inter VM communication plagued with the same issues as Binder?"
tags = ['kernel', 'linux', 'threat-modeling', 'audit', 'arm']
toc = true
+++
# TL;DR

- **No vulnerability (that I found) on the interesting "Hostile peer" surface that is open source.** Everything Binder does for you inside the kernel — framing, length, type, sender identity — IVC delegates to a layer that isn't in the tree. 
- **Coming from Binder, the first thing you notice is everything that isn't there.** No device node, no ioctl, no uapi header. Three `u32`s on the wire,
  and no length, type, identity or sequence field among them. Zero allocations,  zero loops and zero locks in the whole file.
- **The classic shared-ring bug isn't present, and not by accident.** The remote end supplies counters, a state word and message bytes, but never the index used to compute an address. That holds even against a remote writing every byte of both shared regions. Good job killing the Type, Length, Value (TLV) paradigm that causes so much trouble!

# Tegra IVC 101
## Why look at it?
I come from a Android background, as such I have paid my dues against binder, like all good researchers do, and have the scars to prove it. As a IPC surface I thought it would be interesting to compare and contrast. 

Someone told me about this new AI thing if you have heard of it. Apparently NVIDIA is plays a part in this new hotness, figuratively and literally if you have turned your laptop into a heater via query. 

I have no Tegra hardware, no hypervisor and no guest on the machine I read this on, and this was my own reading of public source, on my own time, against no hardware and no customer. This would also help determine if I wanted to do more work on Nvidia.
## What is it?

It's a lock-free single-producer/single-consumer ring in a block of memory two processors both map. I will be using the terms `local` and `remote` in this breakdown. Think of `local` as a vetted service, which need not be linux, but does need to comply with the IVC protocol.  Think of `remote` as the untrusted guest, running linux of some flavor. 

Concretely: `remote` writes a message into slot N of a fixed array, then bumps a counter. `local` watches the counter move, reads slot N, and bumps a
counter of its own. That's the whole mechanism — two free-running counters and an array of fixed-size slots, one such array per direction, `remote` -> `local`, `local` -> `remote`. The code terms this relationship a `peer`. There can be many peers but for the purpose of understanding we will focus on 1 peer relationship. 
## What uses it?

### DRIVE OS — one Linux guest beside a rack of service partitions

The shape that actually ships today, a dirty Linux guest full of who know what apps and an ostensibly safe set of peers trying to make sure the dirty Linux guest doesn't explode your car. In other words, a type-1 hypervisor whose entire partition set is frozen at build time by the **PCT** (Platform Configuration Table). Beside the single Linux guest sit roughly ten small **service partitions**. I do not know if each of these services is a `peer` in the sense of IVC but I will continue under that assumption.

> [!danger] I have not RE'ed the Hypervisor, QNX, or any other services provided by DriveOS. Therefore it is only my inference from the design/docs that these services are each a `peer`

![DriveOS block diagram](/static/tegra_teardown/archi_foundation_image3.png)

A few things fall out of that picture.

- **The `local` end is a service partition, and it isn't Linux.** The far side of every IVC line is an HVRTOS binary. That's the concrete version of the "need not
  be Linux, does need to comply with the protocol" definition above.
- I am reading "Guest Operating System" as could be QNX or LINUX
- I am inferring that SoC resource calls go to the HyperVisor through a standard hypercall implementation and not IVC.
### IGX Thor — a Linux VM beside a QNX safety VM

The other one,  NVIDIA's IGX gives two architectures for Thor, the second being *"NV Hypervisor, supporting a Linux VM and a QNX VM on CCPLEX."*

![IGX Thor stack](/static/tegra_teardown/full-stack-platform-for-enterprise-edge-ai.jpg)

# Tegra IVC from the lens of Binder

Binder is the IPC I know best, so it's the ruler I reached for. Both are in-kernel IPC between two parties that don't trust each other symmetrically. That is close
to the end of the resemblance.

|                             | Binder                                                                                                               | Tegra IVC                                    |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| Core file                   | `binder.c`, 7,294 lines                                                                                              | `ivc.c`, **721**                             |
| uapi                        | `binder.h` — 640 lines, 14 ioctls, 21 `BC_` commands, 24 `BR_` returns, 7 object types                               | none                                         |
| On the wire                 | target, cookie, `code`, `flags`, `sender_pid`, `sender_euid`, `data_size`, `offsets_size`, plus a typed object array | three `u32`s — two counters and a state word |
| Userspace entry             | `misc_register`, openable by any app                                                                                 | none in-tree                                 |
| Allocation on the data path | 14 sites, plus a per-process buffer allocator                                                                        | **0**                                        |
| Loops                       | 43                                                                                                                   | **0**                                        |
| Locks, atomics, refcounts   | 79                                                                                                                   | **0**                                        |

A Binder transaction describes itself. It says what it is (`code`), how long it is (`data_size`), what objects it carries (a typed array with seven possible types,
including file descriptors), and who sent it, classic TLV. An IVC message says a counter moved.

The identity row is the one that matters most, and it's one line of kernel:

```c
t->sender_euid = task_euid(proc->tsk);
```

The sender doesn't supply that. The kernel fills it in from the sending task, which is the entire reason Binder can be an authorization surface — every
`checkCallingUid()` in the framework above it is resting on that assignment. IVC has nothing to forge because it has no field to forge. It also has no way to tell
you who's on the other end.

So the two files fail in different places. Binder's risk is concentrated in the kernel's own bookkeeping: an object graph, reference counts, a per-process buffer allocator, and seventy-nine lock, atomic and refcount operations. That's a lot of state to keep straight while parsing something an untrusted app wrote. `ivc.c` keeps no state of that kind at all — no allocation, no loop, no lock — and a file with nothing to get wrong mostly doesn't.

**That's the trap.** Anyone actually using IVC needs everything Binder has: framing, length, type, identity, ordering. Those requirements don't evaporate because the ring declines to provide them. They move. In-tree they move up into `bpmp.c`, or down into the hypervisor. So all of the good stuff is probably in the hypervisor if I had to guess, and closed source is typically a softer target than open source in my experience.

Which means the comparison flatters IVC only if you compare files. Compare the fraction of the system you can actually read and it inverts: Binder's whole protocol is upstream — the parser, the object graph, the allocator, the locking, all in one directory, all readable by anyone with a checkout. With IVC, the 721 lines are the part that's upstream, and they're also the part with almost nothing in them.

Now go back to `/dev/ivc<N>`. "No userspace entry point" reads is a property of mainline. Nvidia ships a character device onto the same ring, with an `ioctl` on it.

[ivc-cdev.c](https://gitlab.com/nvidia/nv-tegra/linux-nv-oot/-/blob/l4t/l4t-r36.2/drivers/virt/tegra/ivc-cdev.c)
```c
static const struct file_operations ivc_fops = {
	.owner		= THIS_MODULE,
	.open		= ivc_dev_open,
	.release	= ivc_dev_release,
	.llseek		= noop_llseek,
	.read		= ivc_dev_read,
	.write		= ivc_dev_write,
	.mmap		= ivc_dev_mmap,
	.poll		= ivc_dev_poll,
	.unlocked_ioctl = ivc_dev_ioctl,
};
```

# Let's Audit Some Code!
Now that we know the shape of the Tegra IVC surface what are we looking for? Well, the killer bug would be if we could manipulate a peer somehow. Could we get some memory corruption on the "safe" `local` guest via IVC from a hostile `remote` peer? How about an illegal state transition? 

This points squarely at the shared memory as the attack surface. A hostile guest is bound only by the permissions of the hypervisor so there is no need to conform to IVC in the sense of honoring its protocol. 
## The Shared Memory
Two rings, one for tx, one for rx. Each has a 128B header which is padded out for cache coherency, in fact most of it is padding. You will also have some number of frames following the header of some size.  
![Possible mem layouts](/static/tegra_teardown/mem_params.png)
### Thoughts on Hypervisor permissions for the shared memory
I was not going to RE the Hypervisor. So I had to make some assumptions about what the permissions of the given memory were. The problem here is that I dont know any implementation that has permissions granular enough to handle what this IVC implementation does. Essentially this implementation would need 64B granularity. That is because there is a 128B header where the `tx` side needs to write to the first half and the `rx` side needs to write to the second half (how that works we will cover below). If the hypervisor does not support this and only supports the page level permissions I am used to it could be a big problem depending on the IVC Caller implementation as page level permissions allow a hostile peer to at the very least read or write both rings header values, and most likely some or all of the data. 

Two things would need to happen in order for a direct compromise of a peer based on IVC via shared memory and ivc.c claims responsibility for neither of them: 
1. Hypervisor doesn't support permission granularity down to 64B
2. The Caller of IVC on the `local` (non-hostile side) needs to do something with the data that is useful for exploitation
I am not looking at the Callers or the Hypervisor in this post so I am giving them the benefit of the doubt based on some documentation regarding the Thor platform. 
## It's a small surface
But, I continued looking at it through the lens of binder so I thought fuzzing it would be no problem based on concepts from the great Android Red Team blog [binder-fuzzing](https://androidoffsec.withgoogle.com/posts/binder-fuzzing/) by Zi Fan Tan, Gulshan Singh,  and Eugene Rodionov. 

So that's what I did. I setup the Linux Kernel Library (LKL), with a little harness to dumb fuzz the shared IVC memory acting as the hostile `remote` peer while transitioning through operations on the `local` guest. 
## What's on the wire

Each direction gets a 128-byte header: a 32-bit counter and a state word for the transmit half, a counter for the receive half, padding. 
```c
struct tegra_ivc_header {
	union {
		struct {
			/* fields owned by the transmitting end */
			u32 count;
			u32 state;
		};

		u8 pad[TEGRA_IVC_ALIGN];
	} tx;

	union {
		/* fields owned by the receiving end */
		u32 count;
		u8 pad[TEGRA_IVC_ALIGN];
	} rx;
};
```

That's the whole on-wire vocabulary. No length field, no type field, no offset, no sequence number, no magic, no identity of the sender. Framing, length and type are somebody else's job. Not much to fuzz...
### But where's the data at?
What is the point of Inter VM communication if you are not communicating anything? Well, that is where IVC says "Not my problem." again. While IVC does name the data `frame`, the buffers used are provided by the caller, the frame size is calculated by the caller, the number of frames are set by the caller. IVC does not touch the frames, it only lets the caller know when they are ready (see step 5 below). 
#### Write Example
![IVC Write](/static/tegra_teardown/write_simple.png)

#### Why not include the frame(s) in the fuzzing runs?
For a few reasons:
- The goal was to target just the IVC implementation so I considered this scope creep because the data was handled by the caller not the implementation
- You clearly get enough rope to hang yourself with as the caller. 
	- This is true for many exported kernel functions. 
-  I didnt really care about crashing or gaining execution on my own vm ( was assuming that anyway ) I want to affect the peer.

This does become a problem under the userspace LPE threat model though, so its something I would test if I were considering `ivc-cdev.c` in the nvidia oot as well. 
## State machine
Due to the fact that we essentially have two 32bit words to play with as the hostile peer, `count` and `state`, it's imperative that the state machine be checked as that is 50% of our attack surface, lol. At first glance the state space is tiny `enum tegra_ivc_state {TEGRA_IVC_STATE_ESTABLISHED = 0, TEGRA_IVC_STATE_SYNC, TEGRA_IVC_STATE_ACK};`, that's it, so you can only have `3^2 == 9` `local`/`remote` states. 

There is a comment in the code which talks though the expected transitions to an established connection:
```
>  *	local	remote	action
>  *	-----	------	-----------------------------------
>  *	SYNC	EST	    <none>
>  *	SYNC	ACK	    reset counters; move to EST; notify
>  *	SYNC	SYNC	reset counters; move to ACK; notify
>  *	ACK	    EST	    move to EST; notify
>  *	ACK	    ACK	    move to EST; notify
>  *	ACK	    SYNC	reset counters; move to ACK; notify
>  *	EST	    EST	    <none>
>  *	EST	    ACK	    <none>
>  *	EST	    SYNC	reset counters; move to ACK; notify
```
Once the the connection is established the following states may be moved through:

Further, the actions possible are very limited at first glance. 
```
  ┌─────┬─────────────────────────────────────┬────────────────────┬──────────┐                                                     
  │  #  │               action                │      address       │  value   │  
  ├─────┼─────────────────────────────────────┼────────────────────┼──────────┤  
  │ 1   │ tx.count = 0                        │ tx.map + 0         │ constant │    
  ├─────┼─────────────────────────────────────┼────────────────────┼──────────┤    
  │ 2   │ rx.count = 0                        │ rx.map + 64        │ constant │   
  ├─────┼─────────────────────────────────────┼────────────────────┼──────────┤  
  │ 3   │ tx.position = 0                     │ local struct       │ constant │                                                  
  ├─────┼─────────────────────────────────────┼────────────────────┼──────────┤
  │ 4   │ rx.position = 0                     │ local struct       │ constant │
  ├─────┼─────────────────────────────────────┼────────────────────┼──────────┤ 
  │ 5   │ tx.state = SYNC | ACK | ESTABLISHED │ tx.map + 4         │ constant │ 
  ├─────┼─────────────────────────────────────┼────────────────────┼──────────┤                                                     
  │ 6   │ dma_sync, 64 bytes                  │ fixed offset       │ —        │
  ├─────┼─────────────────────────────────────┼────────────────────┼──────────┤ 
  │ 7   │ ivc->notify(ivc, ivc->notify_data)  │ fn ptr set at init │ —        │
  └─────┴─────────────────────────────────────┴────────────────────┴──────────┘  
```
What can make this state machine complex is that a peer can change state at any given time. So let's say as a caller using IVC you have just called `tegra_ivc_write_get_next_frame`, or as a caller you are in the middle of filling a frame or something. IVC's answer to this is again "Not my problem", there is no locking. 
### Now that I know better, fuzz better
So now that I know a bit more about the state machine, it's time to make the fuzzer less dumb. Since I am already using LKL, and I am already inspired by Android Red Team's blog on fuzzing binder it makes sense to continue on that path. In that blog they describe one of the interesting characteristics of LKL. It is a single process, in order to do task management it has to yield, no background task, no async work (in the general meaning, workqueues still work just serially against everything else), this can be a pain in the ass, or an opportunity. The clever people who wrote the blog used it as an opportunity to coerce what looked like racy conditions into being fuzzed by using the single process yielding substrate of LKL to interleave threads with an amount of control that would otherwise not be possible. 

Let's follow that example, find some janky looking transition points, and see if we can get a our hostile `remote` peer interleaved with our well behaved `local` in a way that might affect `local`.
#### Potential Jank point 1, notification interleave
State is only changed on call to `tegra_ivc_reset` or `tegra_ivc_notified` , note that `tegra_ivc_notified` is action #7. There are only two calls to IVC for a write `get_next_frame` and `advance`, so that makes it simple where to try and target a state change, right in between those two calls. Can we get one of those state changed based actions to trigger a desync between the two calls such as `tx.count == 54` -> `get_next_frame` -> `notify` ->  `notified` -> `tx.count == 0` -> `advance`, would this make `advance` work on `54` or `0`? This means it might not be a corruption that ASAN could catch since its within the given allocation. Therefore one addition was needed to the fuzzer that wasn't in the red team blog. I needed some type of oracle in the harness to show that the frame sent was the frame read. 
#### Potential Jank point 2, state machine
State machines are hard. While this one is tiny and the corresponding actions are trivial there are two possibilities which look plausible for affecting a peer. 
- Can we force an illegal state transition that hot loops a peer (DoS)?
- Can we hold a hold a state that hot loops the peer (DoS)?
This is seems plausible because there are no sleeps or waits, or anything I could see that prevents a peer from retrying a move through the state graph as fast as possible.
## Let the fuzzer run...
Now that the fuzzer is a little smarter and finding somethings lets build the mental model a bit more and take a look at one of the few safety checks that exist.
#### tegra_ivc_check_params
```c
static int tegra_ivc_check_params(unsigned long rx, unsigned long tx,
				  unsigned int num_frames, size_t frame_size)
{
	// Lots of alignment checks cut for size.

	if (rx < tx) {
		if (rx + frame_size * num_frames > tx) {
			pr_err("queue regions overlap: %#lx + %zx > %#lx\n",
			       rx, frame_size * num_frames, tx);
			return -EINVAL;
		}
	} else {
		if (tx + frame_size * num_frames > rx) {
			pr_err("queue regions overlap: %#lx + %zx > %#lx\n",
			       tx, frame_size * num_frames, rx);
			return -EINVAL;
		}
	}

	return 0;
}
```
This overlap check makes sense, we dont want `tx` and `rx` rings clobbering each other. Let's do some Desk Checking:
if `tx == 100`, `frame_size == 5`, `num_frames == 1`, and `rx == 105`, that should have `tx` and `rx` butt right up against each other but not overlap since 5 bytes would be at addrs 100, 101, 102, 103, 104 right?
So tx is `100 + 5 * 1 == 105` and `rx < tx` does not hold in this case so we use the bottom check. No problem, `105 (tx + frame_size * num_frames) > 105 (rx) == false` we pass the check as we should. 

Can we use a zero somewhere, that always trips people up? So `tx == 100`, `frame_size == 0`, `num_frames == 1`, and `rx == 100` should be interesting because in the case we did above `rx` and `tx` were the same number and passed. Again we fall through to the bottom check because (100 < 100) does not hold. So we end up with `100 (tx + frame_size * num_frames) > 100 (rx) == false` we pass the check and we shouldn't... 

Is this a bug? Yes, in the sense that it is specifically trying to check for overlap and it missed a case. However, as a caller you can by design do so much worse already. Further, in the threat model of dorking with a peer this provides nothing, it would only confuse your VM's setup and prevent comms to the peer as a caller since both your `rx` and `tx` queues are stacked on each other per below. So a correctness bug at most.
``` 
addr 100                                                     addr 128            addr 128 (no increase due to frame_size == 0)
    ┌───────────────────────────────────────────────────────────────┬──────────────────┐        
tx  | tegra_ivc_header {count, state, <pad>} tx, {count, <pad>} rx  |     frames       |
    ├───────────────────────────────────────────────────────────────┼──────────────────┤  
rx  │ tegra_ivc_header {count, state, <pad>} tx, {count, <pad>} rx  |     frames       |   
    └───────────────────────────────────────────────────────────────┴──────────────────┘  
```

BUT WAIT... my diagram is wrong... I had a mental model of the tx/rx queue that I used to write the diagram for this bug which included the header. The header is not included in `check_params`?!? Really what `check_params` just did was allow this:
``` 
addr 100           addr 100 (no increase due to frame_size == 0)
    ┌──────────────────┐        
tx  |     frames       |
    ├──────────────────┤  
rx  │     frames       |   
    └──────────────────┘  
```
When it was trying to enforce this by code:
``` 
addr 100       addr 105 ( if frame_size == 5 and 1 frame)
    ┌─────────────┬────────────┐        
    |  tx frames  |  rx frames | 
    └─────────────┴────────────┘  
```
But really intended to enforce this:
``` 
addr 100                      addr 233                       addr 366 ( hdr + frame_size 5, 1 frame)
    ┌────────────────┬─────────────┬────────────────┬────────────┐        
    | tx ivc_header  | tx frames   |  rx ivc_header | rx frames  | 
    └────────────────┴─────────────┴────────────────┴────────────┘  
```
Otherwise this is just a frame overlap check, and that is problematic since frames might not overlap but maybe its possible that a `tegra_ivc_header` could overlap with frames since the header is not counted... More desk checking:
Let's use the `frame_size == 5` and `num_frames == 1`since gives us something smaller than the header (128) give `check_params` which lets us "not overlap" with just 5 bytes, we know this passes from the first example. 
``` 
addr 100,addr 105        addr 228
    ┌────────────────────────┬──────────────────┐        
tx  | ivc_header             |     frames       |
    └────────────────────────┴───┬──────────────┴─────┐  
rx        │ ivc_header           |     frames         |   
          └──────────────────────┴────────────────────┘  
    └──┬──┘
     checker says we have space for one 5B frame, no overlap, we good.
```
Is this now anything more than a correctness bug? I would still classify this as a correctness bug within `ivc.c`

This is due to how little responsibility the IVC implementation takes. As I have said before IVC pushes the hard work mostly up to the caller, but what we care about here in order to judge whether this is a correctness or security issue depends on whether the hypervisor took up the deferred responsibility of managing the memory.  So if it is a security issue, that issue is in the hypervisor permission granularity and its a bigger problem than this. 
## Check the fuzzer
### What happend with janky code point 1

Ironically, if the in-tree caller implementation had followed the guidance in `ivc.h` there would be a real finding here:
```c
/**
 * tegra_ivc_notified - handle internal messages
 * @ivc		pointer of the IVC channel
 *
 * This function must be called following every notification.
 *
 * Returns 0 if the channel is ready for communication, or -EAGAIN if a channel
 * reset is in progress.
 */
int tegra_ivc_notified(struct tegra_ivc *ivc);
```
### What happend with with janky code point 2
Suspicion confirmed. There appears to be a DoS which can be triggered by a hostile VM. Essentially, the Attacker can reach a state where it sets it's `SYNC` state and walks away. The victim then hot loops forever. 

This is problematic because the context of this Tegra IVC is that you have `x` number of peers, one for each service, on a SoC with `y` number of cores. So if as the attacker you DoS more peers than there are cores  things stop working not just for the one VM but everything running on the SoC.  Concerning if this intergrates with your vehicle (DriveOS), or industrial/medical equipment (IGX Thor)

In more detail:
![DoS peer hotloop](/static/tegra_teardown/DoS_statemachine.png)
The loop is absorbing, not slow. Nothing about the state differs between pass 1 and pass 7,651,085 (crash dump below). No path inside `tegra_ivc_notified()` can  change the victim's `rx` word, so `rx_state == SYNC` holds forever. Each pass rewrites the `ACK` already in `tx.state` (`:468`), re-zeroes both counters (`:452-453`), rings the doorbell (`:474`), and returns `-EAGAIN` (`:549-550`) because `tx_state` is not `ESTABLISHED`. 

I feel resonably confident that this is a true bug and not something the hypervisor is mediating even without looking at the hypervisor itself.  The assumption I made earlier is that this IVC setup works off of 64B fully coherent cache-lines which can have permissions set. That assumption prevents me from thinking there is any way a hypervisor could mediate state transistions without breaking performance which is clearly important based on the comments:
```
ivc.c:46-52 — "delineates ownership of the cache lines, which is critical to    
  performance and necessary in non-cache coherent implementations."
``` 

#### So how does binder handle this issue? 
Basiclly the way I infered that the hypervisor cant. It mediates, and it uses a copy per transaction, slow. The kernel in this case is the mediator rather than a hypervisor. It never shares memory with an untrusted peer, so the attacker method of setting a state in shared memory and walking away cant exist. 
#### If that is too slow whats the fix?
My first thought is that the dangerous bit of this is the DoS of the SoC, not just a DoS of a single peer channel, so a geometric backoff should work. No state change, then dont hot loop, simple right?

But VMs have been around for a minute and they are not really my area so let's check what the cool kids are doing. This cant be the first time IVC problems like this have arrison. Let's take a look at how [Xen](https://xenproject.org/) handles this: 
##### One servicer per peer                                                                                                        
`struct xenvif` holds `struct xenvif_queue *queues`, and each queue gets two kthreads of its own, created per queue in xenvif_connect_queue():              
```c
interface.c:730   kthread_run(xenvif_kthread_guest_rx, queue, ...)     
interface.c:741   kthread_run(xenvif_dealloc_kthread, queue, ...)      
```
A frontend that stalls its own kthread. Compare bpmp-tegra186.c:317-322, where one thread walks all five channels and the first to wedge blocks the rest.   
##### The servicer blocks instead of spinning 
`xenvif_wait_for_rx_work()` (rx.c:570-592) is a hand-rolled wait loop.
That is the per-peer event-driven servicer, verbatim. No spinning; the thread sleeps and the conditions that matter wake it.                            
##### Stall detection that parks and recovers
```c
rx.c:520   xenvif_rx_queue_stalled() // !stalled && slots < needed  && time_after(jiffies, last_rx_time + stall_timeout)                       
rx.c:532   xenvif_rx_queue_ready()  // stalled && slots >= needed     
```
On stall, `xenvif_queue_carrier_off()` sets `queue->stalled = true` (interface.c:728) and drops the carrier, which discards queued packets (interface.c:795) rather than accumulating them. `xenvif_rx_queue_ready()` un-stalls when the frontend starts consuming again. Timeout from `rx_stall_timeout_msecs` (interface.c:516).           
This is the green "park and report" edge, implemented and recoverable — and note it's a timeout, which confirms the same constraint Tegra has when considering fixes: Xen also  cannot distinguish slow (i.e. boot) from malicious without a clock, so it uses one.
##### Per-peer resource quota, with policy outside the kernel                                                                                              
Token-bucket shaping per queue: credit_bytes, credit_usec, credit_timeout (common.h:208-212), enforced in tx_credit_exceeded() (netback.c:810-831) and  checked before accepting each request (netback.c:954). 

Xen puts this knob in the VM's configuration.
##### A loud, fatal way to declare one peer dead
```c
  netback.c:222  static void xenvif_fatal_tx_err(struct xenvif *vif)
                 netdev_err(vif->dev, "fatal error; disabling device\n");
                 vif->disabled = true;
```

  Invoked when the frontend's ring metadata is impossible — e.g. claiming more slots than the ring holds (netback.c:252, :259). One vif dies loudly; the host is fine.
  
A sharp contrast with IVC. Xen's analogue of the over-full condition is a protocol violation that kills the channel and logs it. IVC's over-full check refuses reads silently, permanently, and the handshake still reports ESTABLISHED.
##### Geometric backoff 
```c
  drivers/xen/events/events_base.c:597-644, xen_irq_lateeoi_locked():

  if ((1 << info->spurious_cnt) < (HZ << 2))
          info->spurious_cnt++;
  if (info->spurious_cnt > threshold) {
          delay = 1 << (info->spurious_cnt - 1 - threshold);
          if (delay > HZ)
                  delay = HZ;
          info->eoi_time = get_jiffies_64() + delay;
  }
  ...
  } else {
          info->spurious_cnt = 0;      /* progress resets it */
  }
```

A per-event-channel count of spurious notifications, doubling the delay before re-enabling the interrupt, capped at HZ, and reset to zero the moment a notification turns out to be real. 

Nice! My geometric backoff idea does work for a hypervisor. They have some real defense-in-depth though.
#### The patch
There are a lot of open questions since I have not looked at the hypervisor(s), for this issue in particular the question is: Does the hypervisor enforce some usage limit that prevents a DoS accross the SoC? My educated guess is to say that some of them might, most likely the newer implementations (IGX Thor). However, this doesn't prevent a victim guest from hot looping with any resource its allow from the hypervisor preventing communication with any other peer. 

The least invasive way I thought to do this is via the geometric backoff. So here is the patch:
```c
 void tegra_ivc_reset(struct tegra_ivc *ivc)
 {
        unsigned int offset = offsetof(struct tegra_ivc_header, tx.count);
 
+       tegra_ivc_resync_restart(ivc);
+
        tegra_ivc_header_write_field(&ivc->tx.map, tx.state, TEGRA_IVC_STATE_SYNC);
        tegra_ivc_flush(ivc, ivc->tx.phys + offset);
        ivc->notify(ivc, ivc->notify_data);
        
@@ -546,6 +664,18 @@ int tegra_ivc_notified(struct tegra_ivc *ivc)
        }
 
+       if (tegra_ivc_header_read_field(&ivc->tx.map, tx.state) != tx_state)
+               tegra_ivc_resync_restart(ivc);
+       else if (tx_state != TEGRA_IVC_STATE_ESTABLISHED)
+               tegra_ivc_resync_wait(ivc);
+
        if (tx_state != TEGRA_IVC_STATE_ESTABLISHED)
                return -EAGAIN;

```

Two functions are created `tegra_ivc_resync_restart` and `tegra_ivc_resync_wait`. No change in state -> start the backoff, change in state -> reset the backoff. 

As I started looking at how to patch this I realized there were more opertunites to hot loop. So I made the patch more generic than what I started with, originally it keyed off of only the SYNC state. 

As a side note this patch also made fuzzing work a bit better. With the hot loop spinning at 1.5 M iterations/s the LKL thread pegged the core and the symbolizer subprocess couldn't make progress on a crash dump. With the backoff armed the loop sits in a bounded wait with `cpu_relax()`, the symbolizer gets CPU, the backtrace completes.
# Close

It is clear that as far as IPC/IVC goes the design decisions made here about as far as you can get from Binder. This has its pros and cons in that the actual IVC implementation attack surface is tiny, a count and a state, that's about it. This could be a deliberate call in that if you have multiple disparate OSs (e.g. Linux and QNX) the contract you need to adhere to is correspondingly tiny. 

However, I think that is where the good news ends. In the Android ecosystem fragmented implementations have been the bane of Android security. This is most recently exemplified by Calif's recent post [here](https://calif.io/research/oempocalypse). And it seem to be that this is the direction that Tegra IVC is moving in, as it takes responsibility for nothing and pushes responsibility mostly to the caller. This means that each use of IVC is suspect:
- Did the caller setup the memory, frame numbers, frame size exactly correct?
	- for all peers?
- Did the caller allow for any race conditions (e.g. between calls and notifications)?
- Is a peer even using `ivc.c` or did they roll their own?
- If using `ivc.c` which tree did it come from?

This kind of fragmentation is tech-debt Google has been digging out of for years with the latest being the push for Generic Kernel Images (GKI). Binder though has not suffered such a fate, it is a single implementation not left up to the OEMs and absolutely hammered by the security community until it is one of the hardest attack surfaces on Android. 

Maybe this is my bias talking, but I think my suggestion to Nvidia would be to follow Binder's example. They are in the same space of security critical devices, both embedded, both having to deal with untrusted vendor shenanigans. Fragmentation may buy security through obscurity, but that only works until one stack implementation is important enough to be a target, and I don't know a company who doesn't want their tech to be important.
# Future work
As it stands I probably wont look much more at Tegra. If I do it is obvious that `ivc.c` is not the target, caller implementations, `ivc-cdev.c` or something else adjacent to `ivc.c` is what I would look at. Maybe the Hypervisor depending on what the agrements are to get it.

# Notes
1. NVIDIA documents two steps. **I/O coherency** — *"a feature with which an I/O device such as a GPU can read the latest updates in CPU caches"* — is *"supported on Tegra devices starting with Xavier SOC"*, and is one-way. **Sysmem Full Coherency** — *"an extension to I/O coherency where additionally the CPU can also read the latest updates in the GPU's cache"* — is *"supported on Tegra devices starting with Thor SoC"* and *"removes the need to perform both CPU and GPU cache management operations when the same physical memory is shared between CPU and GPU, and cached on both"* ([CUDA for Tegra, *I/O Coherency*](https://docs.nvidia.com/cuda/cuda-for-tegra-appnote/index.html#i-o-coherency)). Separately, the programming guide splits platforms by page table: hardware-coherent ones *"offer a logically combined page table for both CPUs and GPUs"* and are *"coherent at cache-line granularity instead of page-size granularity"*, against software-coherent ones with separate tables ([Unified Memory, *CPU and GPU page tables*](https://docs.nvidia.com/cuda/cuda-programming-guide/04-special-topics/unified-memory.html#cpu-and-gpu-page-tables-hardware-coherency-vs-software-coherency)). The docs establish *coherency* at cache-line granularity on a Thor-class part. It says nothing about *permission* at that granularity: **neither document mentions access permissions, protection granularity, hypervisor page tables or the SMMU at all**. Coherency decides which agent observes whose writes; permission decides which agent may write. A part can be fully coherent at 64 B and still enforce access control only at 4 KiB: the permission granule is a property of the MMU, not of the coherence fabric. So the 64-byte-permission premise is **assumed** for this post.
2. ```
   [ivc] step 0: V_NOTIFIED(0,0,0,0) ret=0 flags=0x0
[ivc] step 1: SET_STATE(0,3,3907815483,0) ret=0 flags=0x0
[ivc] step 2: V_WRITE_ADVANCE(0,0,0,0) ret=0 flags=0x0
[ivc] step 3: V_WRITE_ADVANCE(0,0,0,0) ret=0 flags=0x0
[ivc] step 4: SET_COUNT(0,0,0,0) ret=0 flags=0x0
[ivc] step 5: SET_STATE(0,1,1346213513,0) ret=0 flags=0x0
[ivc] step 6: V_WRITE_ADVANCE(0,0,0,0) ret=0 flags=0x0
[    0.315222] fuzz_ivc: ORACLE 4.2.1 notified()==0 with tx.state != ESTABLISHED FIRED [mode=P step=10 armed=0x077 fatal=0x000 geom=0]: notified() returned 0 but the victim's tx.state is now 2 (pre-call pair tx=0 rx=1)
[ivc] step 7: V_NOTIFIED(0,0,0,0) ret=0 flags=0x8
[    5.315939] Kernel panic - not syncing: fuzz_ivc: NOTIFY_LOOP did not terminate: victim spun 7651085 times in 5000000633 ns from node (v=2,a=1) — tegra_ivc_notified() returns -EAGAIN for ever and bpmp-tegra186.c:155-156 never exits
[    5.316010] ---[ end Kernel panic - not syncing: fuzz_ivc: NOTIFY_LOOP did not terminate: victim spun 7651085 times in 5000000633 ns from node (v=2,a=1) — tegra_ivc_notified() returns -EAGAIN for ever and bpmp-tegra186.c:155-156 never exits ]---
lkl_libf_ivc: lib/posix-host.c:451: void panic(void): Assertion `0' failed.
==1320583== ERROR: libFuzzer: deadly signal
    #0 0x467548 in __sanitizer_print_stack_trace (/mnt/ramdisk/ivc_h3_fuzzer/lkl_libf_ivc+0x467548) (BuildId: a4c1c3dea26e5973093d200e0e70fd96b842e13b)
    #1 0x43dbdc in fuzzer::PrintStackTrace() (/mnt/ramdisk/ivc_h3_fuzzer/lkl_libf_ivc+0x43dbdc) (BuildId: a4c1c3dea26e5973093d200e0e70fd96b842e13b)
    #2 0x4236aa in __covrec_810869138693A016 xarray.c
    #3 0x78f910c45caf  (/usr/lib/x86_64-linux-gnu/libc.so.6+0x45caf) (BuildId: 066527e430a32768d82741e00b81eebb1a872294)
    #4 0x78f910ca61ab in __pthread_kill_implementation nptl/pthread_kill.c:43:17
    #5 0x78f910ca61ab in __pthread_kill_internal nptl/pthread_kill.c:89:10
    #6 0x78f910ca61ab in pthread_kill nptl/pthread_kill.c:100:10
    #7 0x78f910c45b7d in raise signal/../sysdeps/posix/raise.c:26:13
    #8 0x78f910c288eb in abort stdlib/abort.c:77:3
    #9 0x78f910c29978 in __libc_message_impl libio/../sysdeps/posix/libc_fatal.c:138:3
    #10 0x78f910c3bf74 in __libc_message_wrapper assert/../include/stdio.h:203:3
    #11 0x78f910c3bf74 in __assert_fail assert/assert.c:37:3
    #12 0x46ffaf in __covrec_64B97C43602C787A /home/dev/repos/lkl_linux/tools/lkl/lib/posix-host.c:451:2
    #13 0x4bd946 in __covrec_CDEACDC7C57EEC97 /home/dev/repos/lkl_linux/arch/lkl/kernel/setup.c:29:2
    #14 0x1b9e2d6 in __covrec_979C81FDA6829769 /home/dev/repos/lkl_linux/kernel/panic.c:474:9
    #15 0x14e8f75 in h3_do_notify_loop /home/dev/repos/lkl_linux/drivers/firmware/tegra/fuzz_ivc.c:1209:4
    #16 0x14e8f75 in h3_run_step /home/dev/repos/lkl_linux/drivers/firmware/tegra/fuzz_ivc.c:1666:9
    #17 0x14e8f75 in h3_ioctl_step /home/dev/repos/lkl_linux/drivers/firmware/tegra/fuzz_ivc.c:2750:8
    #18 0x14e8f75 in __covrec_225BA13D825218E1u /home/dev/repos/lkl_linux/drivers/firmware/tegra/fuzz_ivc.c:2850:10
    #19 0x759419 in vfs_ioctl /home/dev/repos/lkl_linux/fs/ioctl.c:51:10
    #20 0x759419 in __do_sys_ioctl /home/dev/repos/lkl_linux/fs/ioctl.c:907:11
    #21 0x759419 in __covrec_1B6E8FFA1BE381E2 /home/dev/repos/lkl_linux/fs/ioctl.c:893:1
    #22 0x4c0f31 in run_syscall /home/dev/repos/lkl_linux/arch/lkl/kernel/syscalls.c:46:8
    #23 0x4c0f31 in __covrec_DB78CF01CB8EDE62 /home/dev/repos/lkl_linux/arch/lkl/kernel/syscalls.c:127:8
    #24 0x468de1 in lkl_sys_ioctl /home/dev/repos/lkl_linux/./tools/lkl/include/lkl/asm/syscall_defs.h:518:1
    #25 0x468de1 in __covrec_E8110637874ACB83 /home/dev/repos/lkl_linux/tools/lkl/tests/fuzzing/libfuzzer/ivc/lkl_ivc_ioctl.c:139:9
    #26 0x4685c3 in __covrec_F89A7E0200F9376 /home/dev/repos/lkl_linux/tools/lkl/tests/fuzzing/libfuzzer/ivc/lkl_ivc_harness.c:217:7
    #27 0x4678d8 in __covrec_8C75E7CDB6CD3B0 /home/dev/repos/lkl_linux/tools/lkl/tests/fuzzing/libfuzzer/ivc/lkl_ivc_main.c:328:2
    #28 0x424bb9 in __covrec_496D1264D4010148 xarray.c
    #29 0x40da64 in __covrec_AC0ED1F2A2A684CC xarray.c
    #30 0x413887  (/mnt/ramdisk/ivc_h3_fuzzer/lkl_libf_ivc+0x413887) (BuildId: a4c1c3dea26e5973093d200e0e70fd96b842e13b)
    #31 0x43e536 in main (/mnt/ramdisk/ivc_h3_fuzzer/lkl_libf_ivc+0x43e536) (BuildId: a4c1c3dea26e5973093d200e0e70fd96b842e13b)
    #32 0x78f910c2a600 in __libc_start_call_main csu/../sysdeps/nptl/libc_start_call_main.h:59:16
    #33 0x78f910c2a717 in __libc_start_main csu/../csu/libc-start.c:360:3
    #34 0x408004 in __covrec_FDAFC01825E84114 xarray.c

   ```
3. 