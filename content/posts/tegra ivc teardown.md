+++
title = 'Tegra IVC Teardown'
date = 2026-10-05T00:00:00Z
draft = false
description = "Is Tegra's Inter VM communication plagued with the same issues as Binder was?"
tags = ['kernel', 'linux', 'threat-modeling', 'audit', 'arm']
toc = true
+++
## TL;DR

Short answer to the question is Tegra's IVC (Inter-VM Communication) plagued with the same issues as Binder? In a word, no. 
- **No memory corruption on the interesting "hostile peer" surface.** Everything Binder does for you inside the kernel (framing, length, type, sender identity) IVC delegates to a different layer.
- **Coming from Binder, the first thing you notice is everything that isn't there.** No device node, no ioctl, no uapi header. Three `u32`s on the wire, and no length, type, identity or sequence field among them. Zero allocations, zero loops and zero locks in the whole file.
- **The DoS: park on `SYNC` and walk away.** The peer parks its state word on `SYNC` and stops touching the ring; the victim's `tegra_ivc_notified()` returns `-EAGAIN` forever (7,651,085 passes in 5 s in my harness) and the caller's retry loop never exits. The one in-tree caller, `bpmp-tegra186.c:155-156`, has exactly that loop. I wrote a geometric-backoff patch: the same trap drops from 7,651,085 passes in 5 s to 64, on every channel at once, but the loop still never exits.
- **The classic shared-ring bug isn't present, and not by accident.** The `remote` end supplies counter, state word and message bytes, but never an index used to compute an address. That holds even against a `remote` writing every byte of both shared regions, which turns out to be the normal case rather than the worst one (see [What review changed](#what-review-changed)). Good job killing the Type, Length, Value (TLV) that causes so much trouble!
## Tegra IVC 101
### Why look at it?
I come from an Android background, as such I have paid my dues against Binder, like all good Android researchers do, and have the scars to prove it. As an inter-process communication (IPC) surface I thought it would be interesting to compare and contrast since I haven't worked much with any IVC.

Someone told me about this new AI thing so I thought I would poke around in AI adjacent code (stats is *mathmagic*). Apparently NVIDIA plays a part in this new AI hotness, figuratively and literally if you have ever turned your laptop into a portable heater via AI query.

I have no Tegra hardware, no hypervisor, etc. Just some code and a bit of time. So this is testing the water to determine if I wanted to invest more time/money to do more serious work on NVIDIA.
### What is it?

Tegra IVC is a lock-free single-producer/single-consumer ring in a block of memory two processors both map.[1](#bibliography) I will be using `local` for the victim end and `remote` for the attacker end; the [threat model](#threat-model) below pins down what each one is.

Concretely: `remote` writes a message into slot N of a fixed array, then bumps a counter. `local` watches the counter move, reads slot N, and bumps a counter of its own. That's the whole mechanism, two free-running counters and an array of fixed-size slots, one such array per direction, `remote` -> `local`, `local` -> `remote`. The code terms this relationship a `peer`. A peer is a *service* on the other end of one channel, not a VM. One guest can sit behind many services, and one guest can hold many peer relationships at once. DRIVE OS picture below is exactly that shape, a single Linux guest with a channel to each of about ten service partitions. So the number of peers is not the number of guests. For the purpose of understanding we will focus on a single peer relationship.
### What uses it?

#### DRIVE OS — one Linux guest beside a rack of service partitions

The shape that actually ships today, a dirty Linux guest full of who-knows-what apps and an ostensibly safe set of peers trying to make sure the dirty Linux guest doesn't explode your car. In other words, a hypervisor whose entire partition set is frozen at build time by the **PCT** (Partition Configuration Table).[[1]](#bibliography)[[2]](#bibliography) Beside the single Linux guest sit roughly ten small **service partitions**. I do not know for sure if each of the services below is a `peer` in the sense of IVC but I will continue under that assumption based on docs/code.

> **Caveat** I have not reverse-engineered the hypervisor, QNX, or any of the other services DRIVE OS provides. That each of these services is a `peer` in the IVC sense is my inference from the design and the docs, they don't have to be and it's not something I verified.

![DRIVE OS block diagram](/static/tegra_teardown/archi_foundation_image.png)

A few things fall out of that block diagram.
- **The `local` end is a service partition, and it isn't Linux.** The far side of every IVC line is an HVRTOS binary. [2](#bibliography) [3](#bibliography) That's the concrete version of the victim in the threat model below: not Linux, but speaking the same protocol.
- I am reading "Guest Operating System" as meaning it could be QNX or Linux.
- I am inferring that SoC (system-on-chip) resource calls go to the hypervisor through a standard hypercall implementation and not IVC.

Here is that same shape in motion, and what one of those channels actually is: two rings in shared memory, one per direction. It also sets up the naming the rest of the post leans on, where the guest's TX ring is the service's RX ring, and the reply ring is the service's TX.

![One guest, its service peers, and what a peer ring is](/static/tegra_teardown/peer_ring.mp4)

#### IGX Thor — a Linux VM beside a QNX safety VM
The other one, NVIDIA's IGX gives two architectures for Thor, the second being "NV Hypervisor, supporting a Linux VM and a QNX VM on CCPLEX."[4](#bibliography) CCPLEX is the CPU complex (Arm application cores) so that sentence is putting both guests on the same cluster rather than on separate processor islands.

![IGX Thor stack](/static/tegra_teardown/full-stack-platform-for-enterprise-edge-ai.jpg)

### Threat model

What I'm attacking is `ivc.c` itself: the protocol implementation, independent of any particular caller.

- **The victim (`local`)** is an endpoint running `ivc.c` the way its header says to: `tegra_ivc_notified()` after every doorbell, `get_next_frame()` followed by `advance()`. I'm assuming a well-behaved caller on purpose. A caller that breaks the contract is a caller bug, not a protocol bug.
- **The attacker (`remote`)** is the other endpoint of the same channel, e.g. a compromised Linux guest talking to a service it's legitimately connected to. It is not a third party reaching into some other guest's channel; that would take a hypervisor mapping the wrong memory, which is a different, and much worse, bug.
- **What the attacker controls:** whatever it can write in the channel's shared memory, at any time, in any order. It doesn't have to follow the protocol, run `ivc.c`, or be honest about its state. In practice that's every byte of both rings, for reasons in [the permissions section](#thoughts-on-hypervisor-permissions-for-the-shared-memory).
- **What counts as a finding:** the victim corrupting memory, publishing or consuming a different frame than the one its caller asked for, or getting stuck in a state it can't leave. Basically, anything that turns "the peer misbehaved" into "the victim misbehaved."
- **Out of scope:** frame contents (parsing them is the caller's job, more on that below), the hypervisor itself, and NVIDIA's out-of-tree `ivc-cdev.c` userspace interface.

The protocol is symmetric, both ends run the same state table, so nothing here depends on which end is Linux. That's what makes it relevant to something like DRIVE OS, where the attacker is the Linux guest and the victim is a service partition that isn't Linux at all. The caveat: I haven't seen the service partitions' implementation. If they run `ivc.c` or a port of it, the results carry over. If they rolled their own, that's its own audit, and there is a likely candidate: NVIDIA's DRIVE OS ships its own IVC library, SIVC, documented as compatible with "Legacy IVC implementations."[20](#bibliography)

Where `bpmp-tegra186.c` comes up, it's one real caller to compare against: does a shipping caller follow the header's guidance, and is a given finding reachable through it? It isn't the attack path. In that driver Linux's peer is BPMP firmware, which already controls Linux's clocks, resets and power, so BPMP misbehaving toward Linux doesn't cross any boundary that matters here since I have already assumed a compromised Linux guest. 
## Tegra IVC from the lens of Binder

Binder is the IPC I know best, so it's the ruler I reached for. Both are in-kernel comms between two parties that don't trust each other symmetrically. That is close to the end of the resemblance.

|                             | Binder                                                                                                               | Tegra IVC                                    |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| Core file                   | `binder.c`, 7,294 lines                                                                                              | `ivc.c`, **721**                             |
| uapi                        | `binder.h` — 640 lines, 14 ioctls, 22 `BC_` commands, 24 `BR_` returns, 7 object types                               | none                                         |
| On the wire                 | target, cookie, `code`, `flags`, `sender_pid`, `sender_euid`, `data_size`, `offsets_size`, plus a typed object array | three `u32`s — two counters and a state word |
| Userspace entry             | `misc_register`, openable by any app                                                                                 | none in-tree                                 |
| Allocation on the data path | 14 sites, plus a per-process buffer allocator                                                                        | **0**                                        |
| Loops                       | 43                                                                                                                   | **0**                                        |
| Locks, atomics, refcounts   | 79                                                                                                                   | **0**                                        |
The loop and lock rows are keyword greps, so treat them as orders of magnitude rather than exact figures, the point is that both are double digits against a hard zero, not the last digit of either.

A Binder transaction describes itself. It says what it is (`code`), how long it is (`data_size`), what objects it carries (a typed array with seven possible types, including file descriptors), and who sent it, classic TLV. A Tegra IVC message says a counter moved.

The identity row is the one that matters most, and it's one line of kernel:

```c
t->sender_euid = task_euid(proc->tsk);
```

The sender doesn't supply that. The kernel fills it in from the sending task, which is the entire reason Binder can be an authorization surface. Every `getCallingUid()` in the framework above it is resting on that assignment. IVC has nothing to forge because it has no field to forge. It also has no way to tell you who's on the other end.

So the two files fail in different places. Binder's risk is concentrated in the kernel's own bookkeeping: an object graph, reference counts, a per-process buffer allocator, and seventy-nine lock, atomic and refcount operations. That's a lot of state to keep straight while parsing something an untrusted app wrote. `ivc.c` keeps no state of that kind at all, no allocation, no loop, no lock, and a file with nothing to get wrong mostly doesn't.

**The trap.** Anyone actually using IVC needs everything Binder has: framing, length, type, identity, ordering. Those requirements don't evaporate because the ring declines to provide them. They move. In-tree they move up into the caller `bpmp` , or down into the hypervisor. While the particular hypervisor for IGX Thor is a statically-partitioned safety kernel with a small TCB (trusted computing base) built to a certification process (per docs) that doesn't mean all hypervisors supporting Tegra IVC will be. The combination of fragmentation problems and closed source could be good grounds for bug hunting.

"No userspace entry point" is a property of mainline. NVIDIA ships a character device onto the same IVC ring, with an `ioctl` on it. e.g. `/dev/ivc<N>` per below. But again, for this post I stick with just the IVC implementation in `ivc.c`.
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

## Let's Audit Some Code!
Now that we know the shape of the Tegra IVC surface what are we looking for? Well, the killer bug would be if we could manipulate a peer somehow. Could we get some memory corruption on the "safe" `local` guest via IVC from a hostile `remote` peer? The surface is tiny, some counters and state, so let's start looking for an illegal state transition and see where that leads us.

Of course this points squarely at the shared memory as the attack surface.
### The Shared Memory
Two rings, one for `tx`, one for `rx`. Each has a 128B header which is padded out for cache coherency, in fact most of it is padding. You will also have some number of frames of some size determined by the caller following the header.

Here is that header from both sides/rings. Note the two memory granule sizes in play, because as an attacker which one is in use could be *cough* pivotal *cough* (I am sorry, I will see myself out...).

![Possible mem layouts](/static/tegra_teardown/mem_params.png)

The ATTACKER/VICTIM labels in that picture are who writes each half *by protocol convention*. The page bar is what the hardware enforces, which is the next section.
#### Thoughts on hypervisor permissions for the shared memory
> **Review** This section changed after review; see [What review changed](#what-review-changed).

I was not going to RE the hypervisor, so the question is what the docs say. The header splits into two 64-byte halves, one written by each end, and the comment at `ivc.c:46-52` is clear about why: it "delineates ownership of the cache lines, which is critical to performance and necessary in non-cache coherent implementations." That's a coherency convention. Nothing enforces it.

Enforcing it would take 64-byte write permissions, and nothing on Tegra offers that. Stage-2 translation and the Arm SMMU grant permissions per translation granule, 4K at the smallest, and in-tree BPMP packs its 256-byte channels sixteen to a 4K page. NVIDIA's own DRIVE OS IVC library says it outright: the shared region must be "mapped into the address space (execution domain) of both sides of the IVC channel with read-write access," because "Both send and receive FIFOs require both read and write access for transitional, backwards compatibility with Legacy IVC implementations."[20](#bibliography)

So for the rest of this post the attacker can read and write every byte of both rings, any time: its own fields, the victim's fields, and every frame in both directions. That's not an exotic assumption. It's the same model Xen and virtio rings live in, and `ivc.c` was clearly written with it in mind; its own comments worry about "a potentially malicious peer" (`ivc.c:111-112`). The interesting part is that `ivc.c` reads some of its *own* fields back out of shared memory (`tx.count` at `:149`, `tx.state` at `:184`, `:211` and `:436`), so the attacker gets a say in what the victim believes about itself, not just about its peer. [Note 1](#notes) has the documentation trail.
### It's a small surface
I continued looking at it through the lens of binder so I thought fuzzing it would be no problem based on concepts from the great Android Red Team blog [binder-fuzzing](https://androidoffsec.withgoogle.com/posts/binder-fuzzing/) by Zi Fan Tan, Gulshan Singh, and Eugene Rodionov.[15](#bibliography)

So that's what I did. I set up LKL, with a little harness to dumb fuzz the shared IVC memory acting as the hostile `remote` peer while transitioning through operations on the `local` guest.
### What's on the wire
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
#### But where's the data at?
What is the point of inter-VM communication if you are not communicating anything? Well, that is where IVC says "Not my problem" again. While IVC does name the data, `frame`, the buffers used are provided by the caller, the frame size is calculated by the caller, the number of frames are set by the caller. IVC does not touch the frames, it only lets the caller know when they are ready (the doorbell, action #7 in the table below: `tegra_ivc_write_advance()` bumps `tx.count` and rings the doorbell when the queue goes from empty to non-empty, `ivc.c:391`, and `tegra_ivc_read_advance()` rings it when the queue goes from full to non-full, `ivc.c:335`. BPMP runs a single frame, so in-tree both conditions always hold and every advance rings).
##### Write Example
![IVC Write](/static/tegra_teardown/write_simple.png)

The address the caller is handed is `tx base + 128 + frame_size × tx.position`, computed from the *local* `position`, never from anything the peer wrote. Step 5 is the caller filling it, `ivc.c` never copies a byte.
##### Why not include the frame(s) in the fuzzing runs?
For a few reasons:
- The goal was to target just the IVC implementation, so I considered this scope creep because the data was handled by the caller, not the implementation.
- I didn't really care about crashing or gaining execution on my own VM (from the attacker perspective). I want to affect the peer.

Data would be a problem under the userspace LPE (local privilege escalation) threat model though, so it's something I would test if I were considering `ivc-cdev.c` in the `nvidia-oot` as well.
### State machine
Three 32-bit words belong to the hostile peer by protocol, two write and one read on the tx ring, and two reads and a write on the rx ring. In my *transmit* ring the peer (local/victim in this case) is the receiver, so `rx.count` there is *its* field by design (`tegra_ivc_advance_rx()`, `ivc.c:159-169`, writes it through the peer's `rx.map`, which is my `tx` ring). The mirror is true for my rx ring. 

So: `tx.count` and `tx.state` in the ring the peer transmits on, `rx.count` in the ring it receives on. It's imperative that the state machine be checked, since it is a third of the whole attack surface, lol. At first glance the state space is tiny `enum tegra_ivc_state {TEGRA_IVC_STATE_ESTABLISHED = 0, TEGRA_IVC_STATE_SYNC, TEGRA_IVC_STATE_ACK};`, that's it, so you can only have `3^2 == 9` `local`/`remote` states. That's the protocol's view. With page-granular permissions the peer can write the victim's state word too, so it can pick both columns of the table below, not just its own.

There is a comment in the code (`ivc.c:410-423`) which talks through the expected transitions to an established connection:
```text
IVC State Transition Table - see tegra_ivc_notified()

local   remote   action
-----   ------   -----------------------------------
SYNC    EST      <none>
SYNC    ACK      reset counters; move to EST; notify
SYNC    SYNC     reset counters; move to ACK; notify
ACK     EST      move to EST; notify
ACK     ACK      move to EST; notify
ACK     SYNC     reset counters; move to ACK; notify
EST     EST      <none>
EST     ACK      <none>
EST     SYNC     reset counters; move to ACK; notify
```
Once you are established, the only transition a peer can force through its own state word is *back down*. (Writing the victim's word directly is the other lever, and what it buys is in [What review changed](#what-review-changed).)

Further, the actions possible are very limited at first glance.
```text
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
Action #7 always fires from `reset()` and from each transition in `notified()`; from the data path it fires only on empty → non-empty (`:391`) and full → non-full (`:335`).

What can make this state machine complex is that a peer can change state at any given time. So let's say as a caller using IVC you have just called `tegra_ivc_write_get_next_frame()`, or as a caller you are in the middle of filling a frame or something. IVC's answer to this is again "Not my problem", there is no locking.
#### Now that I know better, fuzz better
Check the fuzzer, no crashes... :( but now that I know a bit more about the state machine, it's time to make the fuzzer less dumb. Since I am already using LKL, and I am already inspired by Android Red Team's blog on fuzzing Binder it makes sense to continue on that path. In that blog they describe one of the interesting characteristics of LKL. LKL is a single process, in order to do task management it has to yield, no background task, no async work (in the general meaning, workqueues still work just serially against everything else), this can be a pain in the ass, or an opportunity. The clever people who wrote the blog used it as an opportunity to coerce what looked like racy conditions into being fuzzed by using the single process yielding substrate of LKL to interleave threads with an amount of control that would otherwise not be possible.

Let's follow that example, find some janky looking transition points, and see if we can get our hostile `remote` peer interleaved with our well behaved `local` in a way that might affect `local`.
##### Potential Jank point 1, notification interleave
Two names that look alike and are not. 
- `ivc->notify()` is the *outbound* doorbell
	- action #7 in the table above, a callback the caller handed over at init, which `ivc.c` calls to poke the peer.
- `tegra_ivc_notified()` is the *inbound* handler
	- what `ivc.h` says the caller must run after every doorbell it receives, and the **only** place in `ivc.c` that moves the state machine. 
State is only changed by `tegra_ivc_reset()` (`ivc.c:402`) or `tegra_ivc_notified()` (`:468`, `:508`, `:532`), and both of them also fire action #7 on the way out. There are only two calls to IVC for a write, `get_next_frame()` and `advance()`, so that makes it simple where to try and target a state change, right in between those two calls. 

Can we get one of those state-changed actions to trigger a desync between the two calls, such as `tx.position == 1` -> `get_next_frame` -> `notify` -> `notified` -> `tx.position == 0` -> `advance`? Would that make `advance` work on frame 1 or frame 0? (`position` is the local frame index, not the shared `count` on the wire). This means it might not be a corruption that ASAN (AddressSanitizer) could catch since it's within the given allocation. Therefore one addition was needed to the fuzzer that wasn't in the red team blog. I needed some type of oracle in the harness to show that the frame sent was the frame read.
##### Potential Jank point 2, state machine
State machines are hard. While this one is tiny and the corresponding actions are trivial there are two possibilities which look plausible for affecting a peer.
- Can we force an illegal state transition that hot loops a peer (DoS)?
- Can we hold a state that hot loops the peer (DoS)?
This seems plausible because there are no sleeps or waits, or anything I could see that prevents a peer from retrying a move through the state graph as fast as possible.
### Let the fuzzer run...
Now that the fuzzer is a little smarter and running again, let's build the mental model a bit more and take a look at one of the few safety checks that exist.
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
This overlap check makes sense, we don't want `tx` and `rx` rings clobbering each other. Let's do some desk checking:

So: if `tx == 100`, `frame_size == 5`, `num_frames == 1`, and `rx == 105`, that should have `tx` and `rx` butt right up against each other but not overlap since 5 bytes would be at addrs 100, 101, 102, 103, 104, right?
So `tx` is `100 + 5 * 1 == 105` and `rx < tx` does not hold in this case so we use the bottom check. No problem, `105 (tx + frame_size * num_frames) > 105 (rx) == false` we pass the check as we should.

Can we use a zero somewhere, that always trips people up? So `tx == 100`, `frame_size == 0`, `num_frames == 1`, and `rx == 100` should be interesting because in the case we did above `rx` and `tx` were the same number and passed. Again we fall through to the bottom check because (100 < 100) does not hold. So we end up with `100 (tx + frame_size * num_frames) > 100 (rx) == false` we pass the check and we shouldn't...

Is this a bug? Yes, in the sense that it is specifically trying to check for overlap and it missed a case. However, as a caller you can by design do so much worse already. Further, in the threat model of dorking with a peer this provides nothing, it would only confuse your VM's setup and prevent comms to the peer as a caller since both your `rx` and `tx` queues are stacked on each other per below. So a correctness bug at most.
```text
addr 100                                                     addr 228            addr 228 (no increase due to frame_size == 0)
    ┌───────────────────────────────────────────────────────────────┬──────────────────┐        
tx  | tegra_ivc_header {count, state, <pad>} tx, {count, <pad>} rx  |     frames       |
    ├───────────────────────────────────────────────────────────────┼──────────────────┤  
rx  │ tegra_ivc_header {count, state, <pad>} tx, {count, <pad>} rx  |     frames       |   
    └───────────────────────────────────────────────────────────────┴──────────────────┘  
```

BUT WAIT... my diagram is wrong... I had a mental model of the `tx`/`rx` queue that I used to write the diagram for this bug which included the header. The header is not included in `check_params`?!? Really what `check_params` just did was allow this:
```text
addr 100           addr 100 (no increase due to frame_size == 0)
    ┌──────────────────┐        
tx  |     frames       |
    ├──────────────────┤  
rx  │     frames       |   
    └──────────────────┘  
```
When it was trying to enforce this by code:
```text
addr 100       addr 105 ( if frame_size == 5 and 1 frame)
    ┌─────────────┬────────────┐        
    |  tx frames  |  rx frames | 
    └─────────────┴────────────┘  
```
But really intended to enforce this:
```text
addr 100                      addr 233                       addr 366 ( hdr + frame_size 5, 1 frame)
    ┌────────────────┬─────────────┬────────────────┬────────────┐        
    | tx ivc_header  | tx frames   |  rx ivc_header | rx frames  | 
    └────────────────┴─────────────┴────────────────┴────────────┘  
```
Otherwise this is just a frame overlap check, and that is problematic since frames might not overlap but maybe it's possible that a `tegra_ivc_header` could overlap with frames since the header is not counted... More desk checking:
Let's use `frame_size == 5` and `num_frames == 1`, since that gives `check_params` something smaller than the header (128) and lets us "not overlap" with just 5 bytes, we know this passes from the first example. 
```text
addr 100,addr 105        addr 228
    ┌────────────────────────┬──────────────────┐        
tx  | ivc_header             |     frames       |
    └────────────────────────┴───┬──────────────┴─────┐  
rx        │ ivc_header           |     frames         |   
          └──────────────────────┴────────────────────┘  
    └──┬──┘
     checker says we have space for one 5B frame, no overlap, we good.
```
Does this actually work with aligned numbers?
- **The zero case.** `tx == 0x1000`, `rx == 0x1000`, `frame_size == 0`, `num_frames == 1`. `IS_ALIGNED(0, 64)` is *true*, so a zero frame size sails through the alignment check; both addresses are 64-aligned; `rx < tx` is false; `0x1000 + 0*1 > 0x1000` is false. Accepted, with both rings stacked on the same address.
- **The header case.** `tx == 0x1000`, `rx == 0x1040`, `frame_size == 64`, `num_frames == 1`. Everything is aligned, `rx < tx` is false, and `0x1000 + 64*1 == 0x1040 > 0x1040` is false. No problem, and yet the `tx` header occupies `0x1000-0x107F` while the `rx` header occupies `0x1040-0x10BF`, so the second half of the `tx` ring's header is byte-for-byte the first half of the `rx` ring's. The check let two 128-byte headers overlap by 64 bytes because it never counted them.

Is this now anything more than a correctness bug? I would still classify this as a correctness bug within `ivc.c`.

This is due to how little responsibility the IVC implementation takes. As I have said before IVC pushes the hard work mostly up to the caller or down to the hypervisor, but what we care about here in order to judge whether this is a correctness or security issue depends on whether the hypervisor took up the deferred responsibility of managing the memory. And with page-granular permissions both ends can already write every byte of both headers, so letting them overlap hands an attacker nothing it didn't have. In-tree it can't come up at all: BPMP keeps its tx and rx regions in separate 4K allocations.
### Check the fuzzer
#### What happened with janky code point 1
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
The in-tree BPMP driver (Boot and Power Management Processor), the co-processor Linux asks for clocks, resets, power and thermals doesn't do this. Its doorbell path goes straight to `tegra_bpmp_handle_rx()`, and the only place `tegra_ivc_notified()` gets called tree-wide is the reset spin. So the interleave I went looking for can't happen in-tree, which is a property of `bpmp-tegra186.c` not of `ivc.c`. Give the harness a caller that does what the header says and the finding shows up:

```text
[ivc] step  8: V_WRITE_GET_FRAME  ret=0    <- caller is handed frame 1
[ivc] step  9: V_NOTIFIED         ret=0    <- branch A, the rx_state==SYNC arm (ivc.c:438), zeroes tx.position, EST -> ACK
[ivc] step 10: V_RESET            ret=0
    ... resets and one pass through the tx_state==ACK arm (ivc.c:516) put the channel back to ESTABLISHED ...
[ivc] step 20: V_WRITE_ADVANCE            <- succeeds, on frame 0

ORACLE advance acted on a different frame than get_next_frame handed out:
  victim write_advance acted on frame 0 but get_next_frame handed out frame 1
```

That is the `tx.position == 1` -> `get_next_frame` -> `notify` -> `notified` -> `tx.position == 0` -> `advance` sequence from earlier, and the answer to "would this make advance work on frame 1 or frame 0" is **frame 0**.

`get_next_frame` builds the caller's map from `ivc->tx.position`, and the matching `advance` re-reads that field when it runs. Nothing re-reads it into the map and nothing locks it. So the caller fills frame 1, `notified()` lands in between and zeroes the position, the peer drives the channel back to `ESTABLISHED` so the advance no longer fails `-ECONNRESET`, and the advance flushes and publishes **frame 0** (whatever stale bytes happen to be sitting there) to the peer, and the message the caller actually wrote is never sent.

Every address involved is in bounds. The positions get re-based to `0`, which is a legal index for any `num_frames >= 1`, so there is nothing for KASAN, the kernel's AddressSanitizer, to complain about.
##### Why I'm not patching this
It is latent in this tree for two independent reasons: `tegra_ivc_notified()` is never called between `get` and `advance` in-tree, and `bpmp-tegra186.c:134-136` configures `num_frames = 1`, so `tx.position` is permanently `0` and there is nothing to desync.

Take the victim's `rx` ring, the one we transmit into. Those frames are ours. We author every byte in them, and with no locking anywhere we can rewrite one in the middle of the victim's read whenever we feel like it. So say we time a `notified()` to land between its `read_get_next_frame()` and its `read_advance` and make it consume the wrong frame, so what? We wrote all of them. And that's following some semblance of the protocol which as a compromised guest we never had to conform. i.e this didn't hand us anything we were missing.

Now the victim's `tx` ring, the one we receive from. Here we author nothing, but we can read every frame in it, whenever we like, in any order, as many times as we like, without conforming. So a desync that shuffles *which* frame we end up looking at gains us nothing either. They were all already ours to read.

With that context in mind the problem is a desync between the get and advance. So if I were to patch this I think I would add a check flag which could be cleared in `get`, set in `reset` or `notified`, and checked in `advance` so that if there was some desync problem you reset everything do the handshake again, then try the read or write again.
#### What happened with janky code point 2
The attacker sets its state word to `SYNC` and walks away; the victim then hot loops forever.

![The attacker writes SYNC into the shared state word, then goes AFK](/static/tegra_teardown/trap_setup.mp4)

The issue here is not really a DoS of one peer service. This could be done simply by not responding as the attacker, you have "denied a service". The problem, I think, happens when this scales up. A peer is a service, not a VM. In the DRIVE OS shape that is one dirty Linux guest against roughly ten service partitions, and nothing in `ivc.c` makes wedging the tenth harder than wedging the first. So `x` services down, from one guest, is not the part I'm unsure about.

What I can't close is whether `x` services down becomes the SoC down. That needs two things I haven't established: 
- the spinning partitions share physical cores rather than being pinned to their own by the PCT
- the hypervisor enforces no per-partition CPU budget. 
The IGX material up top is a hint and not an answer "a Linux VM and a QNX VM on CCPLEX" puts both on the same CPU complex rather than on separate processor islands, which is the precondition for interference, but sharing a complex is not the same as sharing a core, and the PCT is free to pin them apart.

Pin the partitions, budget them properly, and you have removed the spillover while leaving the per-service kill exactly where it was. A well-configured hypervisor turns a speculative SoC-wide DoS into a dependable per-service one. Better, but not a fix.

How bad the spin is for the victim VM? I think its safe to infer that in the case the hypervisor has a CPU budget if `x` number of services hot looped is greater than the budget that VM is cooked. If there is no hypervisor budget and `x > #cpus` your SoC is cooked. Concerning if this integrates with your vehicle (DRIVE OS) or industrial/medical equipment (IGX Thor), but treat the SoC-wide version as a thing to go and check on hardware if you are so inclined.

In more detail, here is why `tegra_ivc_notified()` can never climb back out of `ACK` once the peer is parked on `SYNC`. Branch A (`:438`) is taken on the peer's word alone, rewrites `ACK` over `ACK` and rings the doorbell, while the `-EAGAIN` at `:549-550` checks the victim's *own* word, which branch A never sets back to `ESTABLISHED`:

![Branch A checks only the peer's word, so the victim never leaves ACK](/static/tegra_teardown/why_stuck.mp4)

The loop is absorbing, not slow. Nothing about the state differs between pass 1 and pass 7,651,085 (full crash dump in Note 2). No path inside `tegra_ivc_notified()` can change the victim's `rx` word, so `rx_state == SYNC` holds forever. Each pass rewrites the `ACK` already in `tx.state` (`:468`), re-zeroes both counters (`:452-453`), rings the doorbell (`:474`), and returns `-EAGAIN` (`:549-550`) because `tx_state` is not `ESTABLISHED`.

I feel reasonably confident that this is a true bug and not something the hypervisor is mediating, even without looking at the hypervisor itself. Once the region is mapped read-write into both ends, which is what NVIDIA's own IVC library requires, no read or write of the state word goes through the hypervisor at all. Mediating would mean trapping every access, and the ownership comment makes it clear performance is the whole point:
```c
ivc.c:46-52 — "delineates ownership of the cache lines, which is critical to    
  performance and necessary in non-cache coherent implementations."
``` 

##### So how does Binder handle this issue?
Basically the way I inferred that the hypervisor can't. It mediates, and it uses a copy per transaction, slow. The kernel in this case is the mediator rather than a hypervisor. It does share memory with the untrusted peer (the per-process buffer is mmap'd into the receiving process) but `binder.c:6161` clears `VM_MAYWRITE`, so the peer can only ever read it. There is no attacker-writable control word anywhere in the mapping, so the attacker method of parking a state in shared memory and walking away doesn't exist.
##### If that is too slow, what's the fix?
My first thought was that the dangerous bit was the SoC-wide DoS, so a geometric backoff should work. No state change, just don't hot loop, simple right?

But VMs have been around for a minute and they are not really my area so let's check what the cool kids are doing. This can't be the first time problems like this have arisen. Let's take a look at how [Xen](https://xenproject.org/) handles it (line numbers below are Linux v6.17-rc5[18](#bibliography)). Specifically `xen-netback`, the *backend* driver that sits in the trusted domain and talks to an untrusted frontend over a shared ring. 
###### One servicer per "peer"
`struct xenvif` holds `struct xenvif_queue *queues`, and each queue gets two kthreads of its own, created per queue in `xenvif_connect_data()` (`interface.c:703`):
```c
interface.c:730   kthread_run(xenvif_kthread_guest_rx, queue, ...)     
interface.c:741   kthread_run(xenvif_dealloc_kthread, queue, ...)      
```
A frontend that stalls its own kthread stalls only itself. 
###### The servicer blocks instead of spinning
`xenvif_wait_for_rx_work()` (`rx.c:570-593`) is a hand-rolled wait loop. It `prepare_to_wait()`s, re-checks `xenvif_have_rx_work()`, and schedule_timeout()`s. That is the per-peer event-driven servicer. No spinning, the thread sleeps and the conditions that matter wake it.
###### Stall detection that parks and recovers
```c
rx.c:520   xenvif_rx_queue_stalled() // !stalled && slots < needed && time_after(jiffies, last_rx_time + stall_timeout)
rx.c:530   xenvif_rx_queue_ready()   // stalled && slots >= needed
```
On stall, `xenvif_queue_carrier_off()` (`rx.c:595`) sets `queue->stalled = true` (`rx.c:599`) and, if it is the first queue to stall, logs `"Guest Rx stalled"` and drops the carrier (`rx.c:603-605`) so new packets are dropped at the door rather than accumulating (`rx.c:655-657`). `xenvif_rx_queue_ready()` un-stalls when the frontend starts consuming again. The same constraint Tegra has when considering fixes: Xen also cannot distinguish slow (i.e. boot) from malicious.
###### Per-peer resource quota, with policy outside the kernel
Token-bucket shaping per queue: `credit_bytes`, `credit_usec`, `credit_timeout` (`common.h:208-212`), enforced in `tx_credit_exceeded()` (`netback.c:811-840`) and checked before accepting each request (`netback.c:955`).
###### A loud, fatal way to declare one peer dead
```c
netback.c:223  static void xenvif_fatal_tx_err(struct xenvif *vif)
                 netdev_err(vif->dev, "fatal error; disabling device\n");
                 vif->disabled = true;
```

Invoked when the frontend's ring metadata is impossible:
- claiming more slots than the ring holds
- using more than `fatal_skb_slots` 
One virtual interface dies loudly the host is fine.
###### Geometric backoff
```c
drivers/xen/events/events_base.c:597-646, xen_irq_lateeoi_locked()
(per-device accounting elided):

        if ((1 << info->spurious_cnt) < (HZ << 2)) {
                if (info->spurious_cnt != 0xFF)
                        info->spurious_cnt++;
        }
        if (info->spurious_cnt > threshold) {
                delay = 1 << (info->spurious_cnt - 1 - threshold);
                if (delay > HZ)
                        delay = HZ;
                if (!info->eoi_time)
                        info->eoi_cpu = smp_processor_id();
                info->eoi_time = get_jiffies_64() + delay;
                ...
        }
        ...
} else {
        info->spurious_cnt = 0;
}
```

A per-event-channel count of spurious notifications, doubling the delay before re-enabling the interrupt, capped at `HZ`, saturated at `0xFF` so the shift can't run away, and reset to zero the moment a notification turns out to be real.

Nice! My backoff idea holds up, and somebody already shipped it.

What Xen says is that backoff is the *floor* and not the fix. Xen has five more layers between a hostile frontend and the host: 
- servicer per peer
- blocking wait instead of a spin
- stall detection on a timeout that parks and recovers
- a per-peer quota with the policy set outside the kernel
- and a loud fatal way to declare one peer dead
IVC has none of them, because IVC has decided none of them are its job.
##### The patch: geometric backoff
There are a lot of open questions since I have not looked at the hypervisor(s), for this issue in particular the question is: Does the hypervisor enforce some usage limit that prevents a DoS across the SoC? My educated guess is to say that some of them might, most likely the newer implementations (IGX Thor). However, this doesn't prevent a victim guest/service from hot looping with any resource it is allowed by the hypervisor preventing communication with any other peer.

The least invasive way I thought to do this is via the geometric backoff. So here is the patch:
```diff
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

Two functions are created, `tegra_ivc_resync_restart()` and `tegra_ivc_resync_wait()`. No change in state -> start the backoff, change in state -> reset the backoff.

It cuts the doorbell rate, the shared-memory traffic and the CPU burn. Measured on the same trap: 7,651,085 passes in 5 s without the patch, 64 with it, about 13 a second, on every channel the peer parks at once ([Note 3](#notes)). It does **not** bound the loop: `tegra_ivc_notified()` still returns `-EAGAIN` for ever and the caller still retries for ever, so the channel is still dead and probe or resume still never completes. As I started looking at how to patch this I realized there were more opportunities to hot loop. So I made the patch more generic than what I started with, originally it keyed off of only the SYNC state.

![The same trap for five seconds: 7,651,085 spins without the patch, 64 with it, and still dead either way](/static/tegra_teardown/patch_compare.mp4)

As a side note this patch also made fuzzing work a bit better. With the hot loop spinning at 1.5 M iterations/s the LKL thread pegged the core and the symbolizer subprocess couldn't make progress on a crash dump. With the backoff armed the loop sits in a bounded wait with `cpu_relax()`, the symbolizer gets CPU, the backtrace completes.

Does it hold if the peer can write the victim's own state word, which per the permissions section it can? Yes, in the sense that matters. A peer that writes once and walks away lets the victim settle into a fixed state within one transition, and from there the backoff grows. Forging the victim's `tx.state` buys at most one reset, because the victim's own write overwrites it on the next pass, so keeping a channel near full speed costs the peer a store per victim pass. That's linear, not amplified, and the doorbell each of those passes rings lands back on the peer anyway.

The one set-and-forget path left is a caller. `tegra_ivc_reset()` restarts the backoff, so a caller that resets and retries on every failure brings the fast loop back with no help from the peer. `bpmp-tegra186.c` resets once per probe or resume, so it's fine.
## Close

It is clear that as far as IPC/IVC goes the design decisions made here are about as far as you can get from Binder. This design has its pros and cons in that the actual IVC implementation attack surface is tiny, a count and a state, that's about it. This could be a deliberate call in that if you have multiple disparate OSs (e.g. Linux and QNX) the contract you need to adhere to is correspondingly tiny.

However, I think that is where the good news ends. In the Android ecosystem fragmented implementations have been the bane of Android security, most recently exemplified by [OEMpocalypse](https://calif.io/research/oempocalypse).[16](#bibliography)

 Each use of IVC is suspect:
- Did the caller set up the memory, frame numbers, frame size exactly correct?
	- for all peers?
- Did the caller allow for any race conditions (e.g. between calls and notifications)?
- Is a peer even using `ivc.c` or did they roll their own?
- If using `ivc.c` which tree did it come from?

This kind of fragmentation is tech-debt Google has been digging out of for years with the latest being the push for Generic Kernel Images (GKI).[17](#bibliography) Binder though has not suffered such a fate, it is a single implementation not left up to the OEMs and absolutely hammered by the security community until it is one of the hardest attack surfaces on Android.

Maybe this is my bias talking, but my suggestion to NVIDIA would be to consolidate in some way. One implementation, in the open, with a shared conformance suite, hammered by everyone until it stops giving. That is perfectly compatible with a tiny wire contract; it's the *implementations* of the stack that need to stop being fragmented. The five things Xen has and IVC doesn't, per-peer servicing, a blocking wait, a stall timeout, a per-peer quota, and a loud way to declare a peer dead would be a good place to start though.

Fragmentation may buy security through obscurity, but that only works until one implementation stack is important enough to be a target, and I don't know a company that doesn't want their tech to be important.
## Future work
As it stands I probably won't look much more at Tegra. If I do it is obvious that `ivc.c` is not the target, caller implementations, `ivc-cdev.c` or something else adjacent to `ivc.c` is what I would look at. Maybe the hypervisor depending on what the agreements are to get it. Review turned up some concrete places to start:
- **SIVC**, NVIDIA's DRIVE OS IVC library and the likely implementation on the service side.[20](#bibliography) Only three of its functions are publicly documented.
- **NVIDIA's out-of-tree stack already goes past what mainline guarantees.** `tegra_ivc_channel_sync()` in `ivc_ext.c` sets each private position from the shared counter, modulo `num_frames`, right after init.[21](#bibliography) Bounded, so not an out-of-bounds bug, but with both ends able to write everything the peer picks the victim's starting slot.
- **Callers that reset and retry.** `tegra_ivc_reset()` restarts the backoff, so a caller that resets on every failure undoes it.
- **A harness peer that doesn't hold still during a loop**, so the per-pass forging case is a run and not just an argument.
- **Better coverage of the victim's send frames** ([Note 3](#notes)).
## Prior work

I do things a bit different in my workflow. I dont like to look at prior work until I have some reasonable mental model of what I am looking at. I think looking at other peoples work in the space before you have poked around yourself invites bias and could essentially nullify anything helpful about having a second person looking at it i.e. you might miss bugs. That said, at some point I do look at prior work.

I could not find published security work on `ivc.c` or the IVC ring protocol. What comes back is the source on Bootlin's Elixir, the original patch threads on lore,[19](#bibliography) and NVIDIA's own docs, no advisories, no talks, no writeups.[7](#bibliography) 

Everything I could find on Tegra itself is boot chain and silicon. Fusée Gelée and ShofEL2, Katherine Temkin and fail0verflow, independently, sharing CVE-2018-6242. They turn an attacker-controlled copy length in the bootROM's USB recovery stack into code execution before any signature check gets a say. [8](#bibliography) [9](#bibliography) selfblow does it one stage later: `nvtboot` loads `nvtboot-cpu` without checking the load address first. [10](#bibliography) Bittner and friends glitch `VDD_SYS_SOC` until the bootROM re-enables `NvBootUartDownload()`, a hidden bootloader NVIDIA fuses off in shipping parts, and walk out with the whole boot ROM and the MB1 keys. [11](#bibliography)

Tegra in a shipping car is Tencent's Keen Security Lab, twice. First CVE-2017-6261, a reference-count bug in the Tegra `nvmap` kernel module on Tesla's infotainment unit, reached from userspace through `/dev/nvmap`. [12](#bibliography) (Their whitepaper is where the mechanism comes from; NVIDIA's own CVE text for 6261 is vaguer and calls it a user-space driver issue.) Then Mercedes' MBUX: the NTG6 head unit's Multimedia Board is a Tegra T18X, and "the hardware can support the Nvidia Tegra hypervisor very well. The hypervisor virtualizes two Linux systems." [14](#bibliography) So somebody has already stood on a production Tegra hypervisor with two guests on it. 

Blade's *Another Road Leads to the Host* has an untrusted guest writing messages into a shared ring, the vGPU plugin `libnvidia-vgpu.so` parsing them inside a root-running `nvidia-vgpu-mgr`, and the researchers turning that into root on the host. [13](#bibliography) Same shape as my threat model. Two things make it a different post: it is NVIDIA's closed x86 datacenter stack, nothing with an Arm core in it, and the bugs are in the message *payload* (frames) which is the one thing I deliberately kept out of the fuzzer since I am not looking at callers here. 
# Notes
## What review changed
Prior work is one half of how I check myself. The other half: I hand it to someone very technical and let them try to break it. This post went through that and came back with questions. Here's what they asked, what I found, and what changed.
#### "What's the attack path?"
The threat model was confusing. Whether I meant a guest writing into the memory a service uses to talk to *another* guest, etc. The answer is now the [Threat model](#threat-model) section. 
#### "Isn't stage-2 4K/16K/64K?"
Some docs I read seemed to imply that Thor hands the header's two 64-byte halves to different writers. The reviewer pointed out that stage-2 and SMMU permissions come in translation granules, 4K at the smallest. So back to the docs I'd cited. Both CUDA documents are about coherency but i read implied permission. Nvidia is a chipmaker, maybe Tegra is built different than stock ARM?

The one I hadn't read was NVIDIA's own DRIVE OS IVC library, SIVC. Its `sivc_init()` requires the whole region be "mapped into the address space (execution domain) of both sides of the IVC channel with read-write access," because "Both send and receive FIFOs require both read and write access for transitional, backwards compatibility with Legacy IVC implementations."[20](#bibliography) Legacy IVC is this protocol. NVIDIA documents the opposite of my assumption: both ends can write every byte.

My first reaction was that if that's true, NVIDIA has bigger problems than this post. It isn't, really. That's how Xen and virtio rings live too, and `ivc.c` was written for it. Frame indices are private and always in bounds, so the no-corruption claim survives. What changes is that `ivc.c` reads some of its *own* fields back out of shared memory, so the peer gets a say in what the victim believes about itself. Which raised the next question.
#### So does the patch still hold?
That one was mine, not theirs. If the peer can write the victim's own `tx.state`, can it get around the backoff, which keys off that word changing?

My harness already had an answer sitting in it. Every input runs in one of three modes, and one of them lets the attacker write the victim's own fields; I'd labeled that case a deployment gap and moved on. The logs show the fuzzer did it about 400,000 times, with no sanitizer findings and no new kind of oracle firing ([Note 3](#notes)).

Then the reasoning. With the peer's state frozen, the victim's own writes settle within one transition, whatever the peer wrote first:

| Peer leaves its state at | Victim ends up | Backoff |
| --- | --- | --- |
| `SYNC` | `ACK`, rewriting the same `ACK` every pass | grows |
| `ACK` | `ESTABLISHED`, so `notified()` returns 0 | the loop exits |
| `ESTABLISHED` or out of the enum, victim at `SYNC` | stays at `SYNC`; no transition applies | grows |
| anything but `SYNC`, victim's own word forged out of the enum | stays at the forged value | grows |

So set-and-forget is capped at about 13 passes a second under either permission model. Forging the victim's word gets the peer one backoff reset per store, which means a store per victim pass. That's not the amplification I was worried about. The case worth a sentence is a caller that resets and retries on every failure, since `tegra_ivc_reset()` restarts the backoff. The [patch section](#the-patch-geometric-backoff) now says all of this.
#### Smaller things
Many, of them... Thanks for taking the time to review my friend!
![brasil flag](/static/tegra_teardown/brasil-flag.png)

### Note 1 — coherency is not permission

NVIDIA documents two steps. **I/O coherency** — *"a feature with which an I/O device such as a GPU can read the latest updates in CPU caches"* — is *"supported on Tegra devices starting with Xavier SOC"*, and is one-way. **Sysmem Full Coherency** — *"an extension to I/O coherency where additionally the CPU can also read the latest updates in the GPU's cache"* — is *"supported on Tegra devices starting with Thor SoC"* and *"removes the need to perform both CPU and GPU cache management operations when the same physical memory is shared between CPU and GPU, and cached on both"* ([CUDA for Tegra, *I/O Coherency*](https://docs.nvidia.com/cuda/cuda-for-tegra-appnote/index.html#i-o-coherency))[[5]](#bibliography). Separately, the programming guide splits platforms by page table: hardware-coherent ones *"offer a logically combined page table for both CPUs and GPUs"* and are *"coherent at cache-line granularity instead of page-size granularity"*, against software-coherent ones with separate tables ([Unified Memory, *CPU and GPU page tables*](https://docs.nvidia.com/cuda/cuda-programming-guide/04-special-topics/unified-memory.html#cpu-and-gpu-page-tables-hardware-coherency-vs-software-coherency))[[6]](#bibliography). The docs establish *coherency* at cache-line granularity on a Thor-class part. It says nothing about *permission* at that granularity: **neither document mentions access permissions, protection granularity, hypervisor page tables or the SMMU (the system-wide memory management unit, or MMU) at all**. Coherency decides which agent observes whose writes; permission decides which agent may write. A part can be fully coherent at 64 B and still enforce access control only at 4 KiB: the permission granule is a property of the MMU, not of the coherence fabric. That gap is why this post originally *assumed* 64-byte permissions. NVIDIA's DRIVE OS IVC library closes it the other way: its `sivc_init()` requires the region be mapped read-write into both ends, for compatibility with "Legacy IVC implementations."[20](#bibliography) So permission is page-granular, and both ends can write everything.

### Note 2 — the full fuzzer run

Full fuzzer output for the `SYNC` hot-loop DoS. Absolute paths and build IDs redacted; everything else is verbatim.

```text
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
==PID== ERROR: libFuzzer: deadly signal
    #0 0x467548 in __sanitizer_print_stack_trace (<build>/lkl_libf_ivc+0x467548)
    #1 0x43dbdc in fuzzer::PrintStackTrace() (<build>/lkl_libf_ivc+0x43dbdc)
    #2 0x4236aa in __covrec_810869138693A016 xarray.c
    #3 0x78f910c45caf  (/usr/lib/x86_64-linux-gnu/libc.so.6+0x45caf)
    #4 0x78f910ca61ab in __pthread_kill_implementation nptl/pthread_kill.c:43:17
    #5 0x78f910ca61ab in __pthread_kill_internal nptl/pthread_kill.c:89:10
    #6 0x78f910ca61ab in pthread_kill nptl/pthread_kill.c:100:10
    #7 0x78f910c45b7d in raise signal/../sysdeps/posix/raise.c:26:13
    #8 0x78f910c288eb in abort stdlib/abort.c:77:3
    #9 0x78f910c29978 in __libc_message_impl libio/../sysdeps/posix/libc_fatal.c:138:3
    #10 0x78f910c3bf74 in __libc_message_wrapper assert/../include/stdio.h:203:3
    #11 0x78f910c3bf74 in __assert_fail assert/assert.c:37:3
    #12 0x46ffaf in __covrec_64B97C43602C787A <lkl>/tools/lkl/lib/posix-host.c:451:2
    #13 0x4bd946 in __covrec_CDEACDC7C57EEC97 <lkl>/arch/lkl/kernel/setup.c:29:2
    #14 0x1b9e2d6 in __covrec_979C81FDA6829769 <lkl>/kernel/panic.c:474:9
    #15 0x14e8f75 in h3_do_notify_loop <lkl>/drivers/firmware/tegra/fuzz_ivc.c:1209:4
    #16 0x14e8f75 in h3_run_step <lkl>/drivers/firmware/tegra/fuzz_ivc.c:1666:9
    #17 0x14e8f75 in h3_ioctl_step <lkl>/drivers/firmware/tegra/fuzz_ivc.c:2750:8
    #18 0x14e8f75 in __covrec_225BA13D825218E1u <lkl>/drivers/firmware/tegra/fuzz_ivc.c:2850:10
    #19 0x759419 in vfs_ioctl <lkl>/fs/ioctl.c:51:10
    #20 0x759419 in __do_sys_ioctl <lkl>/fs/ioctl.c:907:11
    #21 0x759419 in __covrec_1B6E8FFA1BE381E2 <lkl>/fs/ioctl.c:893:1
    #22 0x4c0f31 in run_syscall <lkl>/arch/lkl/kernel/syscalls.c:46:8
    #23 0x4c0f31 in __covrec_DB78CF01CB8EDE62 <lkl>/arch/lkl/kernel/syscalls.c:127:8
    #24 0x468de1 in lkl_sys_ioctl <lkl>/./tools/lkl/include/lkl/asm/syscall_defs.h:518:1
    #25 0x468de1 in __covrec_E8110637874ACB83 <lkl>/tools/lkl/tests/fuzzing/libfuzzer/ivc/lkl_ivc_ioctl.c:139:9
    #26 0x4685c3 in __covrec_F89A7E0200F9376 <lkl>/tools/lkl/tests/fuzzing/libfuzzer/ivc/lkl_ivc_harness.c:217:7
    #27 0x4678d8 in __covrec_8C75E7CDB6CD3B0 <lkl>/tools/lkl/tests/fuzzing/libfuzzer/ivc/lkl_ivc_main.c:328:2
    #28 0x424bb9 in __covrec_496D1264D4010148 xarray.c
    #29 0x40da64 in __covrec_AC0ED1F2A2A684CC xarray.c
    #30 0x413887  (<build>/lkl_libf_ivc+0x413887)
    #31 0x43e536 in main (<build>/lkl_libf_ivc+0x43e536)
    #32 0x78f910c2a600 in __libc_start_call_main csu/../sysdeps/nptl/libc_start_call_main.h:59:16
    #33 0x78f910c2a717 in __libc_start_main csu/../csu/libc-start.c:360:3
    #34 0x408004 in __covrec_FDAFC01825E84114 xarray.c
```


### Note 3 — what the fuzzer actually wrote

The harness runs every input in one of three modes, picked by the input's first byte so that each crash artifact names the mode it ran under:

| Mode | The attacker may write |
| --- | --- |
| P | only its own fields: its `tx.count` and `tx.state`, and its `rx.count` |
| S | P, plus the victim's `rx.count`, which sits inside the attacker's own region |
| W | everything, including the victim's `tx.count`, `tx.state` and frames |

From the campaign logs still on disk (the last 80 child logs of each campaign, August 29 to September 15), 12.8 M inputs with step-level logging:

- **402,249 writes to the victim's own `tx.count` or `tx.state` performed**, all in mode W, in 251,039 inputs. Another 412,061 were refused by the mode gate or skipped.
- **254 writes landed in the victim's send frames.** That part of "every byte" is thinly covered.
- **No KASAN, ASAN, UBSAN or kernel `BUG` report** in any of them. The only `WARNING` lines are an LKL boot message about the `power_supply` class, two per child.
- **Inputs that forged victim fields trip the same oracles as P and S.** The top two are a false `-ENOSPC` (12,773 fires) and `notified()` returning 0 while the victim's `tx.state` isn't `ESTABLISHED` (8,603). New ways to reach known failures, no new kind of failure.
- **With the backoff patch in the build** (September 14 onward), all 32 `NOTIFY_LOOP` traps ran at 12-13 passes a second, against 7,651,085 in 5 s before it.

One limit: within one loop the harness freezes the peer, so it can't express a peer that rewrites the victim's state word between passes. The upkeep argument in the patch section is reasoning, not a run.

## Bibliography

1. NVIDIA, *AV PCT Configuration*, DRIVE OS 6.0.6 Linux SDK Developer Guide — defines the Partition Configuration Table as consisting of "server VMs, service VMs, and NVIDIA DRIVE® AV Guest-OS (GOS) VM configurations", and defines IVC: "Inter-virtual Machine Communication (IVC) facilitates data exchange between two virtual machines over shared memory." <https://developer.nvidia.com/docs/drive/drive-os/6.0.6/public/drive-os-linux-sdk/common/topics/virtualization_guide/avpct.html>
2. NVIDIA, *Bind Partitions*, DRIVE OS 7.0.3 Linux SDK Developer Guide — "A bind process creates a hypervisor image that combines DTB/KERNEL of HVRTOS-servers, Hypervisor kernel, and PCT." <https://developer.nvidia.com/docs/drive/drive-os/7.0.3/public/drive-os-linux-sdk/getting-started/bind_partitions.html>
3. NVIDIA, *Storage Server Architecture*, DRIVE OS 7.0.3 Linux SDK Developer Guide — "An HVRTOS based Storage Server manages the storage device and processes the storage access request from the client VM/HVRTOS process." <https://developer.nvidia.com/docs/drive/drive-os/7.0.3/public/drive-os-linux-sdk/core-concepts/storage_server.html>
4. NVIDIA, *NVIDIA IGX Safety Product Brief* (doc 4473375, Feb 2026), p. 1 — "IGX Thor supports two software safety architectures: > Linux, with RTOS on FSI and sMCU > NV Hypervisor, supporting a Linux VM and a QNX VM on CCPLEX, with RTOS on FSI and sMCU". The same page's block diagram labels the block "CPU Complex (CCPLEX)", separate from "Functional Safety Island (FSI)". <https://developer.download.nvidia.com/assets/igx/robotics-product-brief-igx-thor-safety-4473375.pdf>
5. NVIDIA, *CUDA for Tegra — I/O Coherency*, §3.1-3.2. <https://docs.nvidia.com/cuda/cuda-for-tegra-appnote/index.html#i-o-coherency>
6. NVIDIA, *CUDA C++ Programming Guide — Unified Memory, CPU and GPU Page Tables: Hardware Coherency vs. Software Coherency*, §4.1.1.2.1.2. <https://docs.nvidia.com/cuda/cuda-programming-guide/04-special-topics/unified-memory.html#cpu-and-gpu-page-tables-hardware-coherency-vs-software-coherency>
7. The negative result — the searches themselves. "tegra ivc", "tegra_ivc_notified", "drivers/firmware/tegra/ivc.c", "Tegra inter-VM communication exploit" and variants, in English, against general web search and NVD. What comes back is the source on Bootlin's Elixir cross-referencer, the original patch threads, and NVIDIA's documentation — no advisories, talks or writeups. <https://elixir.bootlin.com/linux/v6.17-rc5/source/drivers/firmware/tegra/ivc.c>
8. Katherine Temkin / ReSwitched, *Vulnerability Disclosure: Fusée Gelée* (CVE-2018-6242), 2018 — "a copy operation whose length can be controlled by an attacker" in the bootROM USB (RCM) stack, "gaining control of the Boot and Power Management processor (BPMP) before any lock-outs or privilege reductions occur". Scored `AV:P`; needs physical USB access and a forced entry into RCM. <https://misc.ktemkin.com/fusee_gelee_nvidia.pdf>
9. fail0verflow, *ShofEL2, a Tegra X1 and Nintendo Switch exploit*, 24 April 2018 — the same RCM bug, sharing CVE-2018-6242; fail0verflow note that "multiple people have independently discovered it by now" and claim priority themselves. <https://fail0verflow.com/blog/2018/shofel2/>
10. Balázs Triszka (balika011), *selfblow* (CVE-2019-5680), July 2019 — `nvtboot` loads `nvtboot-cpu` without validating the load address, "leading to unsigned code execution on the BPMP". Demonstrated on a Jetson TX1 (T210) with Shield TV r30 blobs; the author claims it "affects every single Tegra device released so far", the Nintendo Switch excepted. <https://github.com/balika011/selfblow>
11. Bittner, Krachenfels, Galauner and Seifert, *The Forgotten Threat of Voltage Glitching: A Case Study on Nvidia Tegra X2 SoCs*, FDTC 2021 (arXiv:2108.06131) — glitching `VDD_SYS_SOC` to re-enable `NvBootUartDownload()` on the BPMP, yielding a full boot ROM dump and MB1 decryption. Tegra X2 is Parker / T186. <https://arxiv.org/abs/2108.06131>
12. Nie, Liu, Du and Zhang, Keen Security Lab of Tencent, *Over-the-Air: How We Remotely Compromised the Gateway, BCM and Autopilot ECUs of Tesla Cars*, Black Hat USA 2018 — CVE-2017-6261, a reference-count bug in the Tegra `nvmap` kernel module reached via `/dev/nvmap` on the infotainment CID. NVD's text for the same identifier is vaguer and names a user-space driver; the kernel-module detail is Keen's. <https://i.blackhat.com/us-18/Thu-August-9/us-18-Liu-Over-The-Air-How-We-Remotely-Compromised-The-Gateway-Bcm-And-Autopilot-Ecus-Of-Tesla-Cars-wp.pdf>
13. Wenxiang Qian, Tencent Blade Team, *Another Road Leads to the Host: From a Message to VM Escape on Nvidia vGPU*, Black Hat USA 2021 — guest writes into a virtio ring, the vGPU plugin `libnvidia-vgpu.so` parses it inside the root-running `nvidia-vgpu-mgr`. Two OOB issues and an information leak (CVE-2021-1082/-1084/-1087) chained to root on the host. x86 datacenter vGPU, not Tegra. <https://i.blackhat.com/USA21/Wednesday-Handouts/us-21-Another-Road-Leads-To-The-Host-From-A-Message-To-VM-Escape-On-Nvidia-VGPU.pdf>
14. Keen Security Lab of Tencent, *Mercedes-Benz MBUX Security Research Report*, 2021 — §2.2.1: "On the NTG6 head unit, the Multimedia Board consists of the Tegra T18X SoC. Therefore, the hardware can support the Nvidia Tegra hypervisor very well. The hypervisor virtualizes two Linux systems." Head unit NTG6, shipping in A-, E-Class, GLE, GLS and EQC; CVE-2021-23906/-23907/-23908/-23909. On attacking the hypervisor itself: "the IOMMU is enabled. Eventually we didn't achieve a successful exploit. In the worst case, the hypervisor will panic." <https://keenlab.tencent.com/en/whitepapers/Mercedes_Benz_Security_Research_Report_Final.pdf>
15. Zi Fan Tan, Gulshan Singh and Eugene Rodionov, Android Red Team, *Binder Fuzzing*, August 6, 2025 — the LKL single-thread interleaving idea the harness borrows. <https://androidoffsec.withgoogle.com/posts/binder-fuzzing/>
16. Lukas Maar, Calif, *OEMpocalypse Now: A Generic Exploitation Strategy from Android untrusted app to root*, August 31, 2026 — page use-after-frees in OEM kernel drivers on Samsung, Xiaomi and Oppo/OnePlus/Realme. <https://calif.io/research/oempocalypse>
17. Android Open Source Project, *Generic Kernel Image (GKI) project* — "addresses kernel fragmentation by unifying the core kernel and moving SoC and board support out of the core kernel into loadable vendor modules." <https://source.android.com/docs/core/architecture/kernel/generic-kernel-image>
18. Linux v6.17-rc5, the Xen sources quoted in the backoff section: `drivers/net/xen-netback/` (`interface.c`, `rx.c`, `netback.c`, `common.h`) and `drivers/xen/events/events_base.c`. <https://elixir.bootlin.com/linux/v6.17-rc5/source/drivers/net/xen-netback>, <https://elixir.bootlin.com/linux/v6.17-rc5/source/drivers/xen/events/events_base.c>
19. Thierry Reding, *firmware: tegra: Add IVC library*, commit ca791d7f4256, August 19, 2016 — where `ivc.c` entered mainline. The v3 patch and Stephen Warren's review are the lore threads. <https://github.com/torvalds/linux/commit/ca791d7f4256>, <https://patchwork.ozlabs.org/project/linux-tegra/patch/20160819173233.13260-5-thierry.reding@gmail.com/>, <https://lore.kernel.org/all/a11ba4fb-5be5-7b26-164d-63831d8891c7@wwwdotorg.org/>
20. NVIDIA, *SIVC API*, DriveOS Linux NSR SDK API Reference 7.0.3 — `sivc_init()`: "The IVC Library execution environment shall provide a region of memory that is mapped into the address space (execution domain) of both sides of the IVC channel with read-write access … Both send and receive FIFOs require both read and write access for transitional, backwards compatibility with Legacy IVC implementations." <https://developer.nvidia.com/docs/drive/drive-os/7.0.3/public/drive-os-linux-sdk-api-ref/group__SIVC__API.html>
21. NVIDIA, `linux-nv-oot` (L4T r36.2), `drivers/firmware/tegra/ivc_ext.c` and `drivers/virt/tegra/tegra_hv.c` — the out-of-tree hypervisor driver runs mainline `ivc.c` plus an extension layer; `tegra_ivc_channel_sync()` sets each position from the shared counter modulo `num_frames`. <https://gitlab.com/nvidia/nv-tegra/linux-nv-oot/-/blob/l4t/l4t-r36.2/drivers/firmware/tegra/ivc_ext.c>, <https://gitlab.com/nvidia/nv-tegra/linux-nv-oot/-/blob/l4t/l4t-r36.2/drivers/virt/tegra/tegra_hv.c>
