"""Animations for content/posts/tegra ivc teardown.md.

Three short clips, each dropped beside the paragraph it explains:

    TrapSetup     the attacker writes SYNC into shared memory and walks away
    WhyStuck      why tegra_ivc_notified() can never leave ACK  (the core bug)
    PatchCompare  the busy-wait before and after the backoff patch

Render each with animations/render.py; see the README. No LaTeX: every label,
counter and table cell is Pango text, and the code panes are Pygments-
highlighted Text. Colours are sampled from the original static diagrams so the
clips and any remaining images read as one set.
"""

from manim import *

# --- palette, from static/tegra_teardown/*.png -----------------------------
BG = "#1c1c1c"
PANE = "#141420"
NODE_FILL = "#101028"
PURPLE = "#996df3"
TEXT = "#d6d4cc"
DIM = "#8a8a84"
FAINT = "#44444f"
ATTACK = "#ff8f8f"
GOOD = "#8fd6a0"
CHAN = "#86c5ff"  # channel wires: a bright neutral, distinct from both ends
SANS = "Noto Sans"
MONO = "DejaVu Sans Mono"

# tegra_ivc_notified(), trimmed to branch A and the return. The gutter numbers
# are the real ivc.c lines each display line stands for, so a reader can open
# the file to the same place. v6.17-rc5.
NOTIFIED = [
    ("rx_state = read(peer.tx_state);", 435),
    ("tx_state = read(own.tx_state);",  436),
    ("if (rx_state == SYNC) {", 438),
    ("    tx.count = rx.count = 0;", 452),
    ("    own.tx_state = ACK;", 468),
    ("    notify();", 474),
    ("}", None),
    ("if (tx_state != ESTABLISHED)", 549),
    ("    return -EAGAIN;", 550),
]


def label(s, size=26, color=TEXT, font=SANS, **kw):
    return Text(s, font=font, font_size=size, color=color, **kw)


def fit(mob, width):
    if mob.width > width:
        mob.scale_to_fit_width(width)
    return mob


def word_box(text, edge=PURPLE, width=2.7, fill=NODE_FILL):
    box = RoundedRectangle(corner_radius=0.22, width=width, height=0.75,
                           stroke_color=edge, stroke_width=3,
                           fill_color=fill, fill_opacity=1)
    return VGroup(box, fit(label(text, 24).move_to(box), width - 0.3))


class _CaptionScene(Scene):
    """A scene with one swapped caption line pinned to the bottom edge."""

    def setup(self):
        self.caption_mob = None

    def caption(self, markup, size=26):
        new = fit(MarkupText(markup, font=SANS, font_size=size), 12.6)
        new.to_edge(DOWN, buff=0.4)
        if self.caption_mob is None:
            self.play(FadeIn(new, shift=UP * 0.2), run_time=0.4)
        else:
            self.play(FadeOut(self.caption_mob, shift=UP * 0.2),
                      FadeIn(new, shift=UP * 0.2), run_time=0.4)
        self.caption_mob = new


def code_pane(lines):
    """A Pygments code pane plus a gutter of real ivc.c line numbers.

    Returns (group, body, gutter). body.code_lines[i] is display line i, so a
    highlight rectangle can ride from line to line like a debugger's cursor.
    """
    src = "\n".join(t for t, _ in lines)
    body = Code(
        code_string=src, language="c", add_line_numbers=False,
        formatter_style="dracula", background="rectangle",
        background_config={"fill_color": PANE, "fill_opacity": 1,
                           "stroke_opacity": 0, "buff": 0.35},
        paragraph_config={"font": MONO, "font_size": 22},
    )
    # A gutter number only where a line maps to real source; Text("") is empty
    # and has no bounding box, so skip the blank ones rather than place them.
    gx = body.get_left()[0] - 0.55
    gutter = VGroup()
    for i, (_, n) in enumerate(lines):
        if n is None:
            continue
        g = label(str(n), 15, DIM, font=MONO)
        g.move_to([gx, body.code_lines[i].get_y(), 0]).align_to([gx, 0, 0], RIGHT)
        gutter.add(g)
    return VGroup(gutter, body), body, gutter


def line_cursor(body, i, color=PURPLE):
    r = SurroundingRectangle(body.code_lines[i], color=color, buff=0.06,
                             corner_radius=0.05, stroke_width=3)
    r.stretch_to_fit_width(body.width + 0.2).align_to(body, LEFT).shift(LEFT * 0.1)
    return r


def transition_grid():
    """3x3 next-state grid, rows = local (own) state, cols = remote (peer).

    The whole remote==SYNC column drives local toward ACK; the ACK/SYNC cell is
    the fixed point the DoS parks on.
    """
    cols = ["EST", "ACK", "SYNC"]
    rows = ["SYNC", "ACK", "EST"]
    cells = [
        ["—", "→EST", "→ACK"],
        ["→EST", "→EST", "→ACK"],
        ["—", "—", "→ACK"],
    ]
    tbl = MobjectTable(
        [[label(c, 22) for c in row] for row in cells],
        include_outer_lines=True,
        line_config={"stroke_color": FAINT, "stroke_width": 2},
        h_buff=0.65, v_buff=0.45,
    )
    col_lbls = VGroup(*[label(c, 19, DIM) for c in cols])
    for lbl, cell in zip(col_lbls, tbl.get_columns()):
        lbl.next_to(cell, UP, buff=0.18)
    row_lbls = VGroup(*[label(r, 19, DIM) for r in rows])
    for lbl, cell in zip(row_lbls, tbl.get_rows()):
        lbl.next_to(cell, LEFT, buff=0.3)
    remote = label("peer (remote)", 18, DIM).next_to(col_lbls, UP, buff=0.3)
    local = label("own", 18, DIM).rotate(PI / 2).next_to(row_lbls, LEFT, buff=0.25)
    return VGroup(tbl, col_lbls, row_lbls, remote, local), tbl


def cpu_meter(tracker, color):
    """A 0..1 CPU bar driven by a ValueTracker."""
    frame = RoundedRectangle(corner_radius=0.08, width=3.0, height=0.42,
                             stroke_color=DIM, stroke_width=2, fill_opacity=0)
    bar = always_redraw(lambda: RoundedRectangle(
        corner_radius=0.08, height=0.34,
        width=max(0.001, 2.92 * tracker.get_value()),
        stroke_width=0, fill_color=color, fill_opacity=0.9,
    ).align_to(frame, LEFT).shift(RIGHT * 0.04).set_y(frame.get_y()))
    return VGroup(frame, bar)


def counter(tracker, name, color):
    # The number is redrawn every frame, so it must re-place itself next to the
    # static label; an always_redraw mobject otherwise snaps back to the origin.
    name_mob = label(name, 18, DIM)
    num = always_redraw(lambda: label(
        f"{int(tracker.get_value()):,}", 30, color, font=MONO
    ).next_to(name_mob, RIGHT, buff=0.3))
    return VGroup(name_mob, num)


# ============================================================================
# Clip 2 — WhyStuck : the core bug. Rendered first.
# ============================================================================
class WhyStuck(_CaptionScene):
    def construct(self):
        pane, body, gutter = code_pane(NOTIFIED)
        title = label("tegra_ivc_notified()", 22, TEXT, font=MONO)
        left = VGroup(title, pane).arrange(DOWN, buff=0.3)
        fit(left, 7.0).to_edge(LEFT, buff=0.5).shift(UP * 0.4)

        grid, tbl = transition_grid()
        fit(grid, 4.8).to_edge(RIGHT, buff=0.5).shift(UP * 0.5)

        # --- 1. the two reads, and who owns each word ------------------------
        self.next_section("reads")
        self.play(FadeIn(title), FadeIn(pane), run_time=1.0)
        self.play(FadeIn(grid, shift=LEFT * 0.3), run_time=0.8)
        self.caption(
            f'Every pass reads <span fgcolor="{ATTACK}">the peer’s word</span> '
            f'and <span fgcolor="{GOOD}">its own</span>.')
        peer_read = body.code_lines[0]
        own_read = body.code_lines[1]
        self.play(peer_read.animate.set_color(ATTACK),
                  own_read.animate.set_color(GOOD), run_time=0.8)
        self.wait(1.5)

        # --- 2. branch A checks only the peer's word -------------------------
        self.next_section("branch")
        cur = line_cursor(body, 2, ATTACK)
        self.caption(
            f'Branch A fires on <span fgcolor="{ATTACK}">the peer’s word</span> '
            f'alone — never its own.')
        self.play(Create(cur))
        self.play(Circumscribe(body.code_lines[2], color=ATTACK, run_time=1.4))
        self.wait(0.8)

        # the peer is parked on SYNC, so the whole remote=SYNC column applies
        col_cells = VGroup(*[tbl.get_cell((r, 3)) for r in (1, 2, 3)])
        col_hi = SurroundingRectangle(col_cells, color=ATTACK, buff=0.08,
                                      stroke_width=3)
        self.play(Create(col_hi))
        self.wait(1.2)

        # --- 3. one pass: ACK over ACK, a doorbell, -EAGAIN ------------------
        self.next_section("one_pass")
        self.caption("So own → ACK, ring the doorbell, return -EAGAIN.")
        ack_cell = tbl.get_cell((2, 3))
        fixed = SurroundingRectangle(ack_cell, color=PURPLE, buff=0.05,
                                     stroke_width=4)
        # a small "doorbell", drawn (emoji glyphs render empty in these fonts)
        bell = VGroup(
            Arc(radius=0.22, start_angle=PI, angle=-PI, color=PURPLE,
                stroke_width=4),
            Line([-0.22, 0, 0], [0.22, 0, 0], color=PURPLE, stroke_width=4),
            Dot([0, -0.08, 0], radius=0.05, color=PURPLE),
        ).to_edge(RIGHT, buff=1.1).set_y(-1.6)
        bell_lbl = label("notify()", 15, PURPLE, font=MONO).next_to(bell, DOWN, buff=0.1)
        bell.add(bell_lbl)
        for idx in (3, 4, 5):
            self.play(cur.animate.become(line_cursor(body, idx, ATTACK)),
                      run_time=0.5)
            if idx == 4:
                self.play(Indicate(ack_cell, color=PURPLE, scale_factor=1.15),
                          Create(fixed), run_time=0.6)
            if idx == 5:
                self.play(FadeIn(bell, scale=1.4), Flash(bell, color=PURPLE),
                          run_time=0.6)
                self.play(FadeOut(bell), run_time=0.3)
        self.play(cur.animate.become(line_cursor(body, 8, ATTACK)), run_time=0.5)
        eagain = body.code_lines[8]
        self.play(Circumscribe(eagain, color=ATTACK, run_time=1.0))

        # the own word is what -EAGAIN checks, and branch A never touches it
        self.next_section("never")
        self.caption(
            f'But -EAGAIN checks <span fgcolor="{GOOD}">its own word</span> '
            f'— stuck at ACK, and branch A never sets it.')
        cross = Cross(own_read, stroke_color=ATTACK, stroke_width=4).scale(0.9)
        self.play(own_read.animate.set_color(GOOD),
                  Create(line_cursor(body, 1, GOOD)), run_time=0.6)
        self.play(Create(cross), run_time=0.8)
        self.wait(1.8)

        # --- 4. the loop, readable then at CPU speed -------------------------
        self.next_section("loop")
        self.remove(cross)
        passes = ValueTracker(0)
        pc = counter(passes, "notified() calls", ATTACK).next_to(left, DOWN, buff=0.5)
        self.caption("The caller just calls it again. And again.")
        self.play(FadeIn(pc), cur.animate.become(line_cursor(body, 2, ATTACK)))

        def one_pass(rt):
            seq = [2, 4, 5, 8]
            self.play(Succession(*[
                cur.animate(run_time=rt / len(seq)).become(line_cursor(body, i, ATTACK))
                for i in seq]),
                passes.animate(run_time=rt).increment_value(1),
                Flash(ack_cell, color=PURPLE, flash_radius=0.6, run_time=rt),
                rate_func=linear)

        for _ in range(3):
            one_pass(0.9)
        self.caption("A busy-wait the attacker never has to touch again.")
        self.play(passes.animate.set_value(7_651_085),
                  Succession(*[ShowPassingFlash(
                      line_cursor(body, 2, ATTACK).set_stroke(ATTACK, 6),
                      time_width=0.7, run_time=0.12) for _ in range(22)]),
                  rate_func=rush_into, run_time=3.0)
        self.play(Flash(pc, color=ATTACK, flash_radius=1.0), run_time=0.6)
        self.wait(2.0)


# ============================================================================
# Clip 1 — TrapSetup : one write into shared memory, then gone.
# ============================================================================
class TrapSetup(_CaptionScene):
    def construct(self):
        # two guests over a shared ring, drawn as a strip of byte cells
        atk = word_box("guest\n(attacker)", edge=ATTACK, width=2.6,
                       fill="#281b1b")
        vic = word_box("service\n(victim)", edge=PURPLE, width=2.6)
        atk[1].become(label("guest (attacker)", 20, ATTACK).move_to(atk[0]))
        vic[1].become(label("service (victim)", 20, TEXT).move_to(vic[0]))
        atk.to_edge(LEFT, buff=0.8).shift(UP * 2.1)
        vic.to_edge(RIGHT, buff=0.8).shift(UP * 2.1)

        cells = VGroup(*[
            Square(0.9, stroke_color=FAINT, stroke_width=2,
                   fill_color=NODE_FILL, fill_opacity=1) for _ in range(6)
        ]).arrange(RIGHT, buff=0).move_to(UP * 0.1)
        vals = VGroup(*[label("00", 22, DIM, font=MONO).move_to(c) for c in cells])
        names = ["tx.count", "tx.state", "pad", "pad", "rx.count", "pad"]
        tags = VGroup(*[label(n, 13, DIM).next_to(c, DOWN, buff=0.12)
                        for n, c in zip(names, cells)])
        ring = VGroup(cells, vals, tags)
        ring_lbl = label("shared memory — one 4K page, both ends can write",
                         18, DIM).next_to(cells, UP, buff=0.9)

        self.next_section("layout")
        self.play(FadeIn(atk), FadeIn(vic), run_time=0.8)
        self.play(FadeIn(ring_lbl), *[GrowFromCenter(c) for c in cells],
                  FadeIn(vals), FadeIn(tags), run_time=1.2)
        a_link = Arrow(atk.get_bottom(), cells[1].get_corner(UL), buff=0.15,
                       color=ATTACK, stroke_width=3)
        v_link = Arrow(vic.get_bottom(), cells[1].get_corner(UR), buff=0.15,
                       color=PURPLE, stroke_width=3)
        self.play(GrowArrow(a_link), GrowArrow(v_link))
        self.caption("Two guests, one shared ring. The state word lives at byte 4.")
        self.wait(1.4)

        # --- the attacker types SYNC into tx.state --------------------------
        self.next_section("write")
        self.caption(
            f'The <span fgcolor="{ATTACK}">attacker</span> writes SYNC into '
            f'the state word…')
        target = cells[1]
        box = SurroundingRectangle(target, color=ATTACK, buff=0.04,
                                   stroke_width=3)
        self.play(Create(box), FadeOut(v_link))
        typed = label("01", 22, ATTACK, font=MONO).move_to(target)
        cur = Rectangle(width=0.07, height=0.3, fill_color=ATTACK,
                        fill_opacity=1, stroke_width=0).next_to(typed, RIGHT, buff=0.03)
        self.play(FadeOut(vals[1]), AddTextLetterByLetter(typed, run_time=0.8),
                  FadeIn(cur))
        self.play(Flash(target, color=ATTACK, flash_radius=0.7),
                  FadeOut(cur), run_time=0.6)
        note = label("SYNC", 15, ATTACK).next_to(target, UP, buff=0.12)
        self.play(FadeIn(note, shift=DOWN * 0.1))
        self.wait(1.0)

        # --- and walks away --------------------------------------------------
        self.next_section("afk")
        self.caption("…and never writes again. No upkeep, no protocol.")
        afk = label("AFK", 24, DIM, weight=BOLD).move_to(atk[0])
        self.play(FadeOut(a_link), FadeOut(atk[1]),
                  atk[0].animate.set_stroke(opacity=0.3).set_fill(opacity=0.3),
                  FadeIn(afk), run_time=1.0)
        self.wait(2.0)


# ============================================================================
# Clip 3 — PatchCompare : the busy-wait, before and after the backoff.
# ============================================================================
class PatchCompare(_CaptionScene):
    def construct(self):
        div = DashedLine(UP * 3.2, DOWN * 2.6, color=FAINT, stroke_width=2)

        def side(title, color, x):
            head = label(title, 24, color, weight=BOLD)
            passes = ValueTracker(0)
            cpu = ValueTracker(0)
            pc = counter(passes, "passes in 5 s", color)
            meter = cpu_meter(cpu, color)
            mlbl = label("CPU", 16, DIM)
            col = VGroup(head, pc, VGroup(mlbl, meter).arrange(RIGHT, buff=0.25))
            col.arrange(DOWN, buff=0.6).move_to([x, 0.6, 0])
            return col, passes, cpu

        left, lp, lcpu = side("no backoff", ATTACK, -3.4)
        right, rp, rcpu = side("with the backoff", GOOD, 3.4)

        self.next_section("setup")
        self.play(Create(div), FadeIn(left), FadeIn(right), run_time=1.0)
        self.caption("Same trap, same five seconds. Only the patch differs.")
        self.wait(1.2)

        # --- race both for the same wall-clock 5 s --------------------------
        self.next_section("race")
        self.play(lp.animate.set_value(7_651_085), lcpu.animate.set_value(1.0),
                  rp.animate.set_value(64), rcpu.animate.set_value(0.03),
                  run_time=5.0, rate_func=linear)
        self.play(Flash(left[1], color=ATTACK, flash_radius=1.0),
                  Indicate(right[1], color=GOOD), run_time=0.8)
        self.caption(
            f'<span fgcolor="{ATTACK}">7,651,085</span> spins, core pinned '
            f'— versus <span fgcolor="{GOOD}">64</span>.')
        self.wait(2.0)

        # --- but neither one exits ------------------------------------------
        self.next_section("still")
        for col, c in ((left, ATTACK), (right, GOOD)):
            tag = label("still waiting…", 20, c).next_to(col, DOWN, buff=0.5)
            self.play(FadeIn(tag, shift=UP * 0.1), run_time=0.5)
        self.caption("The backoff stops the heat. The channel is still dead.")
        self.wait(2.5)


def ring_pos(center, r, n, i):
    center = np.array(center, dtype=float)
    ang = PI / 2 - (i % n) * TAU / n          # slot 0 at top, clockwise
    return center + r * np.array([np.cos(ang), np.sin(ang), 0.0])


def ring_buffer(center, r, n, size=0.55):
    """n slot squares arranged on a circle, plus a faint arc showing the flow
    goes *around* the ring (what makes it a ring, not a strip)."""
    slots = VGroup(*[
        Square(size, stroke_color=FAINT, stroke_width=2, fill_color=NODE_FILL,
               fill_opacity=1).move_to(ring_pos(center, r, n, i))
        for i in range(n)])
    flow = Arc(radius=r + 0.5, start_angle=PI / 2 - 0.3, angle=-TAU * 0.78,
               arc_center=np.array(center, dtype=float), color=FAINT,
               stroke_width=2).add_tip(tip_length=0.16)
    return slots, flow


def ring_marker(center, r, n, i, color, letter, pad=0.55):
    """A labelled pointer sitting just outside slot i, tip toward the centre."""
    center = np.array(center, dtype=float)
    p = ring_pos(center, r, n, i)
    d = p - center
    d = d / np.linalg.norm(d)
    tri = Triangle(color=color, fill_opacity=1, stroke_width=0).scale(0.14)
    tri.rotate(angle_of_vector(-d) - PI / 2).move_to(p + d * pad)
    return VGroup(tri, label(letter, 15, color, weight=BOLD).next_to(
        tri, d, buff=0.05))


# ============================================================================
# PeerRing — the DRIVE OS layout, and what one peer "ring" actually is.
# A redraw of static/tegra_teardown/archi_foundation_image3.png as motion.
# Lays the groundwork for the header: guest TX == service RX, guest RX == service TX.
# ============================================================================
class PeerRing(_CaptionScene):
    def construct(self):
        # --- 1. the stack: one guest, a rack of services, one hypervisor ----
        self.next_section("stack")
        hyper = RoundedRectangle(corner_radius=0.1, width=12.0, height=0.7,
                                 stroke_color=FAINT, stroke_width=2,
                                 fill_color=NODE_FILL, fill_opacity=1)
        hyper.to_edge(DOWN, buff=1.4)
        hyper_lbl = label("Hypervisor  (partitions fixed at build by the PCT)",
                          18, DIM).move_to(hyper)

        guest = word_box("Linux guest", edge=ATTACK, width=2.6, fill="#281b1b")
        guest[1].become(label("Linux guest", 20, ATTACK).move_to(guest[0]))
        guest_tag = label("untrusted", 14, DIM).next_to(guest, UP, buff=0.12)
        guest_grp = VGroup(guest, guest_tag).move_to([-5.0, 0.6, 0])

        names = ["BPMP", "Storage", "GPU", "SE", "Debug"]
        svc = VGroup(*[
            VGroup(RoundedRectangle(corner_radius=0.12, width=1.25, height=1.3,
                                    stroke_color=GOOD, stroke_width=2.5,
                                    fill_color="#10281a", fill_opacity=1),
                   label(n, 17, GOOD))
            for n in names])
        for b in svc:
            b[1].rotate(PI / 2).move_to(b[0])
        svc.arrange(RIGHT, buff=0.3).move_to([2.4, 0.6, 0])
        dots = label("· · ·", 24, DIM).next_to(svc, RIGHT, buff=0.25)
        svc_tag = label("service partitions  (HVRTOS, not Linux)", 17, GOOD)
        svc_tag.next_to(svc, UP, buff=0.3)

        self.play(FadeIn(hyper), FadeIn(hyper_lbl), run_time=0.7)
        self.play(FadeIn(guest_grp, shift=UP * 0.2),
                  FadeIn(svc, shift=UP * 0.2), FadeIn(dots), FadeIn(svc_tag),
                  run_time=1.0)
        self.caption(
            f'DRIVE OS: one <span fgcolor="{ATTACK}">Linux guest</span> beside '
            f'a rack of <span fgcolor="{GOOD}">service partitions</span>.')
        self.wait(1.6)

        # --- 2. each channel is a peer --------------------------------------
        self.next_section("peers")
        self.caption(
            f'Each line is one <b>channel</b>. The service on the far end is a '
            f'<span fgcolor="{GOOD}">peer</span> — a service, not a VM.')
        # fan the channels out as curved arcs into the empty space below, so
        # they don't pile up into one near-horizontal smear
        links = VGroup(*[
            ArcBetweenPoints(guest.get_right(), b[0].get_left(),
                             angle=0.3 + 0.16 * i, color=CHAN, stroke_width=3)
            for i, b in enumerate(svc)])
        for ln in links:
            self.play(Create(ln), run_time=0.22)
        self.wait(0.8)
        self.caption("One guest, many peers — about ten of them.")
        self.play(LaggedStart(*[
            ShowPassingFlash(ln.copy().set_stroke(CHAN, 6), time_width=0.8,
                             run_time=0.9) for ln in links], lag_ratio=0.12))
        self.wait(0.8)

        # --- 3. zoom into the BPMP channel: it is TWO rings -----------------
        self.next_section("zoom")
        self.caption("Zoom into one channel. What actually travels it?")
        bpmp = svc[0]
        fade = VGroup(hyper, hyper_lbl, svc[1:], dots, svc_tag, *links[1:])
        self.play(FadeOut(fade), guest_tag.animate.set_opacity(0), run_time=0.8)

        g_end = word_box("Linux\nguest", edge=ATTACK, width=1.9, fill="#281b1b")
        g_end[1].become(label("Linux\nguest", 18, ATTACK).move_to(g_end[0]))
        g_end.move_to([-5.7, 0, 0])
        s_end = word_box("BPMP", edge=GOOD, width=1.9, fill="#10281a")
        s_end[1].become(label("BPMP\nservice", 18, GOOD).move_to(s_end[0]))
        s_end.move_to([5.7, 0, 0])
        self.play(Transform(guest, g_end), Transform(bpmp, s_end),
                  FadeOut(links[0]), run_time=1.0)

        # two rings, side by side: ring A near the guest, ring B near the service
        N, R = 6, 0.9
        ca, cb = np.array([-2.35, 0.35, 0.0]), np.array([2.35, 0.35, 0.0])
        slots_a, flow_a = ring_buffer(ca, R, N)
        slots_b, flow_b = ring_buffer(cb, R, N)
        eqa = MarkupText(f'<span fgcolor="{ATTACK}">guest TX</span>  ≡  '
                         f'<span fgcolor="{GOOD}">service RX</span>',
                         font=SANS, font_size=22).next_to(slots_a, UP, buff=0.5)
        eqb = MarkupText(f'<span fgcolor="{GOOD}">service TX</span>  ≡  '
                         f'<span fgcolor="{ATTACK}">guest RX</span>',
                         font=SANS, font_size=22).next_to(slots_b, UP, buff=0.5)

        self.play(*[GrowFromCenter(s) for s in slots_a],
                  *[GrowFromCenter(s) for s in slots_b],
                  Create(flow_a), Create(flow_b), run_time=1.1)
        self.caption("One channel is <b>two rings</b> in shared memory — "
                     "one per direction.")
        self.wait(1.4)

        def dim(group, arc, v):
            # dim slots/labels normally; the flow arc only by STROKE, or
            # set_opacity fills its interior into a disc.
            return [group.animate.set_opacity(v),
                    arc.animate.set_stroke(opacity=0.5 * v + 0.1)]

        # --- 4. ring A: guest TX == service RX ------------------------------
        self.next_section("ring_a")
        self.play(*dim(VGroup(slots_b, eqb), flow_b, 0.25))
        wa = Arrow(g_end.get_right(), slots_a.get_left(), buff=0.15,
                   color=ATTACK, stroke_width=4)
        self.play(GrowArrow(wa), FadeIn(eqa, shift=DOWN * 0.1))
        self.caption(f'The <span fgcolor="{ATTACK}">guest</span> writes frames; '
                     f'its index walks around the ring.')
        w = ring_marker(ca, R, N, 0, ATTACK, "W")
        r = ring_marker(ca, R, N, 0, GOOD, "R", pad=1.0)
        self.play(FadeIn(w), FadeIn(r))
        fa = VGroup()
        for i in range(3):
            fl = label("f", 15, ATTACK, font=MONO).move_to(ring_pos(ca, R, N, i))
            fa.add(fl)
            self.play(slots_a[i].animate.set_fill(ATTACK, 0.5), FadeIn(fl),
                      Transform(w, ring_marker(ca, R, N, i + 1, ATTACK, "W")),
                      run_time=0.45)
        ra = CurvedArrow(slots_a.get_bottom(), s_end.get_bottom(), angle=-0.9,
                         color=GOOD, stroke_width=4, tip_length=0.2)
        self.caption(f'The <span fgcolor="{GOOD}">service</span> reads behind '
                     f'it — same memory, two names.')
        self.play(Create(ra))
        for i in range(3):
            self.play(slots_a[i].animate.set_fill(GOOD, 0.3),
                      Transform(r, ring_marker(ca, R, N, i + 1, GOOD, "R", pad=1.0)),
                      run_time=0.4)
        self.play(Indicate(eqa, color=TEXT, scale_factor=1.1))
        self.wait(1.2)

        # --- 5. ring B: service TX == guest RX ------------------------------
        self.next_section("ring_b")
        self.play(*dim(VGroup(slots_a, eqa, w, r, fa), flow_a, 0.25),
                  FadeOut(wa), FadeOut(ra),
                  *dim(VGroup(slots_b, eqb), flow_b, 1.0))
        wb = Arrow(s_end.get_left(), slots_b.get_right(), buff=0.15,
                   color=GOOD, stroke_width=4)
        self.play(GrowArrow(wb))
        self.caption(f'The reply ring runs the other way: the '
                     f'<span fgcolor="{GOOD}">service</span> writes, the '
                     f'<span fgcolor="{ATTACK}">guest</span> reads.')
        w2 = ring_marker(cb, R, N, 0, GOOD, "W")
        r2 = ring_marker(cb, R, N, 0, ATTACK, "R", pad=1.0)
        self.play(FadeIn(w2), FadeIn(r2))
        for i in range(2):
            fl = label("f", 15, GOOD, font=MONO).move_to(ring_pos(cb, R, N, i))
            self.play(slots_b[i].animate.set_fill(GOOD, 0.5), FadeIn(fl),
                      Transform(w2, ring_marker(cb, R, N, i + 1, GOOD, "W")),
                      run_time=0.45)
        rb = CurvedArrow(slots_b.get_bottom(), g_end.get_bottom(), angle=0.9,
                         color=ATTACK, stroke_width=4, tip_length=0.2)
        self.play(Create(rb))
        for i in range(2):
            self.play(slots_b[i].animate.set_fill(ATTACK, 0.3),
                      Transform(r2, ring_marker(cb, R, N, i + 1, ATTACK, "R", pad=1.0)),
                      run_time=0.4)
        self.play(Indicate(eqb, color=TEXT, scale_factor=1.1))
        self.wait(1.2)

        # --- 6. groundwork for the header -----------------------------------
        self.next_section("groundwork")
        self.play(FadeOut(wb), FadeOut(rb), FadeOut(w2), FadeOut(r2),
                  *dim(VGroup(slots_a, eqa, w, r, fa), flow_a, 1.0))
        self.caption("Whoever transmits on a ring owns its counter and state "
                     "— that tx/rx split is the header, next.")
        self.play(Indicate(eqa, color=TEXT, scale_factor=1.08),
                  Indicate(eqb, color=TEXT, scale_factor=1.08), run_time=1.6)
        self.wait(2.2)
