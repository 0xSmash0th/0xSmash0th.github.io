+++
title = 'Right for the Wrong Reason'
date = 2026-09-02T00:00:00Z
draft = true
description = 'I read the same 721 lines of kernel source twice under two threat models. The verdict survived. The reason I had written down for it did not.'
tags = ['kernel', 'linux', 'threat-modeling', 'audit', 'arm']
toc = true
+++

I read the same 721 lines of kernel source twice. Same file, same tree, same
line numbers. The only thing I changed between passes was who I imagined on the
other end of the wire.

The second pass reached the same verdict and found that the reason I'd recorded
for it was the weaker of the two I had in hand. It leaned on a constant that one
driver happens to pass, and I'd promoted a property of that driver into a
property of the library it calls.

No confirmed vulnerability came out of either pass. That's not the interesting
part.

## The file

`drivers/firmware/tegra/ivc.c`, 721 lines. Quotes and line numbers throughout are
from 6.17-rc5, which is the tree I read.

It's a lock-free single-producer/single-consumer ring in a block of memory two
processors both map. Concretely: A writes a message into slot N of a fixed array,
then bumps a counter. B watches the counter move, reads slot N, and bumps a
counter of its own. That's the whole mechanism — two free-running counters and an
array of fixed-size slots, one such array per direction.

Each direction gets a 128-byte header: a 32-bit counter and a state word for the
transmit half, a counter for the receive half, padding. Under the second threat
model below, the peer can write every byte of both headers and every byte of
every slot.

That's the whole on-wire vocabulary. No length field, no type field, no offset,
no sequence number, no magic, no identity of the sender. Framing, length and type
are somebody else's job. In-tree the BPMP message driver takes that job. In the
deployment the second half of this post is about, I don't know who does.

Nothing here rests on running anything. There's no Tegra hardware, no hypervisor
and no guest on the machine I read this on, and this was my own reading of public
source, on my own time, against no hardware and no customer.

## Pass one: the peer is signed firmware

First threat model. The peer is the Boot and Power Management Processor — a
separate core on the same die, running the vendor's signed image, which owns the
clock tree, the power domains, thermal, memory-controller scaling and (on T186)
193 reset lines. The vendor's architecture treats it as trusted. The kernel
doesn't drive it. The kernel asks it for permission to run.

The productive hypothesis for any shared-memory ring is the USB one: hostile peer
writes the ring, kernel trusts an index or a length out of the ring, kernel
breaks.

It doesn't hold here. A slot's offset from the start of its region is

```c
sizeof(struct tegra_ivc_header) + ivc->frame_size * frame
```

and `frame` is always one of two positions that live in the driver's own
`struct tegra_ivc`, not in shared memory. The peer supplies counters, a state word
and slot contents. It never supplies the frame index. Three
`WARN_ON(frame >= ivc->num_frames)` guards sit on the frame-access paths anyway.
In the configuration the in-tree caller uses, two of them are short-circuited, so
only one ever runs.

One layer up, the length driving the BPMP message driver's copy out of the peer's
inbox is the *caller's* `msg->rx.size`, validated at 120 bytes or less before
either transfer entry point does anything — so that copy doesn't take a length
from the wire either. That's a property of `bpmp.c` specifically, not a
reassurance about message layers in general.

The conclusion was right. What I wrote down under it was not.

The only in-tree caller passes `num_frames = 1`. Look at what that does to the
advance:

```c
if (ivc->tx.position == ivc->num_frames - 1)
        ivc->tx.position = 0;
else
        ivc->tx.position++;
```

With `num_frames == 1` the test is `0 == 0`, both positions are pinned at zero
forever, and the frame index isn't merely bounded — it's a constant.

The structural reason was sitting right there and I'd already written it out.
When it came time to *close* the item I closed it on the constant, because the
constant is shorter and it's checkable in one line.

## The name on the tin

The Kconfig help text for this library reads:

> IVC (Inter-VM Communication) protocol is part of the IPC (Inter Processor
> Communication) framework on Tegra.

That string — "Inter-VM" — occurs exactly once in the tree, in that help text.
Grep for an inter-VM channel driver, a device-tree binding, a uapi header, a
MAINTAINERS entry: nothing. Every one of the ten exported `tegra_ivc_*` entry
points is called from `bpmp-tegra186.c`, the only in-tree caller outside `ivc.c`
itself.

So the library is named for a deployment with no in-tree instance. That isn't, on
its own, licence to invent a threat model — plenty of Kconfig text is
aspirational, and I nearly left it there.

What changed my mind was noticing that the deployment exists out of tree, is
published, and can be read. Which meant the second model wasn't hypothetical, and
I had no excuse for not running it.

So: the peer is another guest's kernel. It owns its half of the ring outright, it
follows exactly as much of the protocol as it feels like following, and it starts
with no authority over the guest on the other side.

## Re-deriving it without the constant

Before the second pass I wrote down one rule: **never carry a verdict across
models.** Every one re-derived from scratch, or re-affirmed with the reason
written out in full. That's a rule about paperwork, and I'd have skipped it if the
first pass hadn't been so quick. Without it I'd have carried the constant forward
and never known, because the *answer* was going to come out the same either way.

Ten assignments to either position in the whole file, and no others:

- the literal `0`, twice, in `tegra_ivc_init()`
- the literal `0`, twice in each of the two branches of the sync handshake that
  reset a channel
- the literal `0` in the wrap arm of each advance helper
- the guarded `++` in the non-wrap arm of each

`num_frames` and `frame_size` are each written once, from init's parameters.
Nothing on the right-hand side of any of those ten reads shared memory.

The enumeration is a grep; the argument is a one-line induction over what it
returns. Every store is either zero or one past a value already in range, so no
interleaving of the two advance helpers can produce an out-of-range value — the
bound survives a race the protocol might not.

That's better than the reason it replaced, because it holds at frame counts above
one and against a peer writing every byte of both shared regions. But note what it
is: a bound established over `ivc.c`. `struct tegra_ivc` is fully public in
`include/soc/tegra/ivc.h`, positions included, and the *caller* allocates it —
the in-tree one does `devm_kzalloc(bpmp->dev, sizeof(*channel->ivc), ...)`, which
needs the complete type to compile. So the grep proves the bound over one file,
and it holds only while nothing outside that file writes those fields.

I filed that as a caveat. It deserved to be a question.

## The caller I said I couldn't read

NVIDIA publishes an out-of-tree guest driver for exactly the inter-VM deployment
the Kconfig text names — `drivers/virt/tegra/tegra_hv.c`, in the public nv-oot
rel-36 source drop. It calls the same `tegra_ivc_init()` with the mainline
signature, and it passes `nframes` from a structure the hypervisor hands it over
an `hvc` call. (Older L4T releases call a same-named function in a forked copy of
the library, which is its own small version of this post's problem.)

Frame counts of 1, 16 and 64 all appear in the IVC queue tables NVIDIA publishes
in its platform-configuration documentation.

So `num_frames == 1` isn't a fragile assumption. It's a false one, in the
deployment the library is actually named for. The positions finally take values
other than zero, so the `position++` arm and the frame-index multiply it feeds run
for the first time.

Two more things fell out of reading that tree, and neither is a defect in it.

The first is about provenance. Ring geometry doesn't come from device tree; the
guest reads it from the hypervisor and takes it as given. The node itself is real
and required, but the `queues` sub-node documenting `nframes` and `frame-size` is
read by no version of the driver I looked at, R32 through rel-38. I'd been about
to cite that binding as evidence of who supplies the geometry. It would have been
wrong in the same way and for the same reason as the constant — a plausible
artefact describing a path nothing takes.

The second is the one I should have gone looking for. The same drop ships
`ivc_ext.c`, which links against the same `struct tegra_ivc` and exports this:

```c
count = tegra_ivc_header_read_field(&ivc->tx.map, tx.count);
ivc->tx.position = count % ivc->num_frames;
```

That's a position assigned from a counter in the shared header — the eleventh
assignment, in a file my grep never covered, called on every probe by the very
driver I'd just finished citing. The bound itself survives, because the modulo
puts the value back in range. The *proof* doesn't. I'd said the caveat was
hypothetical and that the caller was code I couldn't read, and both halves were
wrong: the caller was sitting in the same directory I'd pulled the frame counts
out of.

That's twice in one file, from the same habit — treating the scope I happened to
grep as the scope the claim was about.

## Two lines, two verdicts, both correct

Two lines of code under a ten-line comment. I'm quoting all of it because the
comment is the argument:

```c
/*
 * Perform an over-full check to prevent denial of service attacks
 * where a server could be easily fooled into believing that there's
 * an extremely large number of frames ready, since receivers are not
 * expected to check for full or over-full conditions.
 *
 * Although the channel isn't empty, this is an invalid case caused by
 * a potentially malicious peer, so returning empty is safer, because
 * it gives the impression that the channel has gone silent.
 */
if (tx - rx > ivc->num_frames)
        return true;
```

Under the firmware model this is a deliberate anti-denial-of-service defence, and
it's the strongest evidence in the file that whoever wrote it had a hostile peer
in mind. That same comment appears verbatim in every other implementation of this
ring I could read, including ARM Trusted Firmware's secure-monitor port — which
is much better evidence that the hostile-peer model is NVIDIA's own than any
single Kconfig string.

Under the hostile-guest model the same two lines read as a cost rather than a
defence, and the comment says why in its own words: the channel is made to look
silent. That's the right trade when the alternative is a trusted peer being
spoofed into believing four billion frames are pending. It's a different trade
when the party who can't tell a silent channel from a lying one is a guest with no
authority over the guest on the other side. The firmware model always has the
counter-argument that a co-processor holding the clock tree could just stop
answering. Between two guests there's nothing equivalent to weigh against it.

**The property is identical, the source is byte-identical, and the two verdicts
disagree.** Neither is wrong. The disagreement isn't an inconsistency to resolve.
It's the result.

I've written before that generated findings tend to be technically correct about
the code and wrong about the threat model. That post was about what triaging them
costs. This is the narrower version: the same thing happened to me, by hand, on my
own work, on the second read — and the artefact carrying the stale assumption
forward was a sentence I'd written down and then believed.

## The bound that lived in a different file

The second reversal, and the one that generalises best.

Pass one asked which callers reach the reset handshake, and closed it by
enumeration. `tegra_ivc_notified()` has exactly one caller in the tree:

```c
static void tegra186_bpmp_channel_reset(struct tegra_bpmp_channel *channel)
{
        /* reset the channel state */
        tegra_ivc_reset(channel->ivc);

        /* sync the channel state with BPMP */
        while (tegra_ivc_notified(channel->ivc))
                ;
}
```

A spin loop in the driver's own reset path. Checkable, true, closed. (My
enumeration of the routes *into* that path turned out to be incomplete too, which
is a smaller instance of the same disease.)

Then I read the header the function is declared in:

> `tegra_ivc_notified` — handle internal messages.
> **This function must be called following every notification.**

The in-tree driver doesn't do that. It calls the function from its reset loop and
nowhere else; the mailbox receive callback goes somewhere else entirely. So my
bound was a property of one driver's deviation from the documented API, not a
property of the library — which means it was never a bound on the library at all.
Anyone integrating from the header, which is the normal way to do it, gets
different behaviour out of the same file.

A closure is only as portable as the file its closing argument cites. When you
close a finding, write down which file the argument came from. If it isn't the
file under audit, you've closed something about a caller, and callers change.

## What I did not find

The deployment the second model is about has no code in either of the public trees
I read, and the vendor drop answers only the smallest of the questions a real one
raises. I can list several more — carveout permissions, whether the doorbell
traps, device-address confinement, what message layer sits on top, reboot
semantics, teardown, the concurrency discipline — and each is capable on its own
of invalidating a premise here. None is answerable by reading more kernel source.

A clean result for this file doesn't extend one line above it. It supplies no
framing, no length and no type, so for a guest deployment every message-level
safety property lives in a layer I couldn't read — and that layer, not this one,
is where I'd expect this family's defects to be.

Two gaps I can name precisely. The doorbell driver the *first* model depends on,
`drivers/mailbox/tegra-hsp.c`, is 1,011 lines and I audited none of it; I opened
about forty lines of its interrupt path to draw a diagram and stopped. (The second
model doesn't go through that file at all — the guest driver rings its doorbell a
different way.)

And the barriers, which are mine to own. There are nine in the file. I tabulated
all nine and checked each against its comment, and once cache maintenance is a
no-op — which it is, for the in-tree caller — they're the only explicit ordering
the file has. What I never did was check whether the pairing holds against a peer
choosing its own store timing, which is the only version of the question that
matters under the second model. Reading a barrier for placement and calling it
reviewed is the same error as the constant, one layer down: I checked the thing
that was easy to check and recorded it as though I'd checked the thing that
mattered.

## Close

What came out of two passes was a disagreement.

The strongest thing I can say about these 721 lines is a negative: a bug class
that's structurally absent, re-derived under the harsher model and better
supported for it. The second strongest is that two honest readings of the same two
lines produce opposite verdicts and neither one is wrong.

Neither is a finding. Both are worth more than the finding would have been.

Both reversals came out of the same habit, which is the only method I'd actually
recommend: write the reason down in full, then check which file it cites. If the
reason is shorter than the structural argument you already had, that's not
efficiency. That's the shape of the mistake.

If I picked this up again I'd start at the barriers, because that's the one place
I know I looked at the easy question instead of the real one. And I still can't
tell you how many hours any of this took. Second post running where I've asked the
field for a number I don't collect about myself.

---

*No vulnerability is claimed here, no defect is named, and there's no reproducer.
Everything quoted from mainline — the Kconfig help text, the over-full comment,
the advance and reset snippets, the `tegra_ivc_notified` contract — is verbatim
from 6.17-rc5 and checkable against public source. The two out-of-tree files are
NVIDIA's, are published, and are cited as such. The claims about my own reading
are mine to assert, and you have only my word for those.*
