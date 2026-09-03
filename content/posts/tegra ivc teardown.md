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
- **Coming from Binder, the first thing you notice is everything that isn't
  there.** No device node, no ioctl, no uapi header. Three `u32`s on the wire,
  and no length, type, identity or sequence field among them. Zero allocations,
  zero loops and zero locks in the whole file.
- **The classic shared-ring bug isn't present, and not by accident.** The remote
  end supplies counters, a state word and message bytes, but never the index used
  to compute an address. That holds even against a remote writing every byte of
  both shared regions. Good job killing the Type, Length, Value (TLV) paradigm that causes so much trouble!

# Tegra IVC 101
## Why look at it?
I come from a Android background, as such I have paid my dues against binder, like all good researchers do, and have the scars to prove it. As a IPC surface I thought it would be interesting to compare and contrast. 

Someone told me about this new AI thing if you have heard of it. Apparently NVIDIA is plays a part in this new hotness, figuratively and literally if you have turned your laptop into a heater via query. 

I have no Tegra hardware, no hypervisor and no guest on the machine I read this on, and this was my own reading of public source, on my own time, against no hardware and no customer. This would also help determine if I wanted to do more work on Nvidia.
## What is it?

It's a lock-free single-producer/single-consumer ring in a block of memory two
processors both map. I will be using the terms `local` and `remote` in this breakdown. Think of `local` as a vetted service, which need not be linux, but does need to comply with the IVC protocol.  Think of `remote` as the untrusted guest, running linux of some flavor. 

Concretely: `remote` writes a message into slot N of a fixed array,
then bumps a counter. `local` watches the counter move, reads slot N, and bumps a
counter of its own. That's the whole mechanism — two free-running counters and an
array of fixed-size slots, one such array per direction, `remote` -> `local`, `local` -> `remote`. The code terms this relationship a `peer`. There can be many peers but for the purpose of understanding we will focus on 1 peer relationship. 
## What uses it?

### DRIVE OS — one Linux guest beside a rack of service partitions

The shape that actually ships today, a dirty Linux guest full of who know what apps and an ostensibly safe set of peers trying to make sure the dirty Linux guest doesn't explode your car. In other words, a type-1 hypervisor whose entire partition set is frozen at build time by the **PCT** (Platform Configuration Table). Beside the single Linux guest sit roughly ten small **service partitions**. I do not know if each of these services is a `peer` in the sense of IVC but I will continue under that assumption.

> [!danger] I have not RE'ed the Hypervisor, QNX, or any other services provided by DriveOS. Therefore it is only my inference from the design that these services are each a `peer`


![DriveOS block diagram](/static/tegra_teardown/archi_foundation_image3.png)

A few things fall out of that picture.

- **The `local` end is a service partition, and it isn't Linux.** The far side of
  every IVC line is an HVRTOS binary. That's the concrete version of the "need not
  be Linux, does need to comply with the protocol" definition above.
- I am reading "Guest Operating System" as could be QNX or LINUX
- I am inferring that SoC resource calls go to the HyperVisor through a standard hypercall implementation and not IVC.
### IGX Thor — a Linux VM beside a QNX safety VM

The other one,  NVIDIA's IGX gives two architectures for Thor, the second being *"NV Hypervisor, supporting a Linux VM and a QNX VM on CCPLEX."*

![IGX Thor stack](/static/tegra_teardown/full-stack-platform-for-enterprise-edge-ai.jpg)

# Tegra IVC from the lens of Binder

Binder is the IPC I know best, so it's the ruler I reached for. Both are in-kernel
IPC between two parties that don't trust each other symmetrically. That is close
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

A Binder transaction describes itself. It says what it is (`code`), how long it is
(`data_size`), what objects it carries (a typed array with seven possible types,
including file descriptors), and who sent it, classic TLV. An IVC message says a counter moved.

The identity row is the one that matters most, and it's one line of kernel:

```c
t->sender_euid = task_euid(proc->tsk);
```

The sender doesn't supply that. The kernel fills it in from the sending task,
which is the entire reason Binder can be an authorization surface — every
`checkCallingUid()` in the framework above it is resting on that assignment. IVC
has nothing to forge because it has no field to forge. It also has no way to tell
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

This points squarely at the shared memory as the attack surface. A hostile guest is bound only by the permissions of the hypervisor so there is no need to conform to IVC in the sense of honoring its protocol. Its a small surface, and to continue looking at it through the lens of binder I though fuzzing it would be no problem based on concepts from the great Android Red Team blog [binder-fuzzing](https://androidoffsec.withgoogle.com/posts/binder-fuzzing/) by Zi Fan Tan, Gulshan Singh,  and Eugene Rodionov. 

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
#### Potential Jank point 1
State is only changed on call to `tegra_ivc_reset` or `tegra_ivc_notified` , note that `tegra_ivc_notified` is action #7. There are only two calls to IVC for a write `get_next_frame` and `advance`, so that makes it simple where to try and target a state change, right in between those two calls. Can we get one of those state changed based actions to trigger a desync between the two calls such as `tx.count == 54` -> `get_next_frame` -> `notify` -> `tx.count == 0` -> `advance`, would this make `advance` work on `54` or `0`? This means it might not be a corruption that ASAN could catch. Therefore one addition was needed to the fuzzer that wasn't in the red team blog. I needed some type of oracle in the harness to show that the frame sent was the frame read. 

## Pass one: the peer is signed firmware

It doesn't hold here. A slot's offset from the start of its region is

```c
sizeof(struct tegra_ivc_header) + ivc->frame_size * frame
```

and `frame` is always one of two positions that live in the driver's own `struct tegra_ivc`, not in shared memory. The peer supplies counters, a state word and slot contents. It never supplies the frame index. Three `WARN_ON(frame >= ivc->num_frames)` guards sit on the frame-access paths anyway. In the configuration the in-tree caller uses, two of them are short-circuited, so
only one ever runs.








## Close



---

