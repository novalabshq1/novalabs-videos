// morning_press physics core (no rendering).
// Circle arena, constant-speed balls, elastic ball-ball collisions, a crushing
// mechanism that only closes when at least one ball is in its capture zone.
// Compiled automatically by sim.py (gcc -O2 -shared -fPIC sim.c -o libsim.so -lm).
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAXB 1600
#define NCOL 8

typedef struct {
  double R, cx, cy, speed, dt;
  int mech;          // 0 = PRESS (2 blocks closing on the centre)
  int axis;          // 0 = blocks move vertically (top/bottom), 1 = horizontally (left/right)
  double W, H, g_open, rod_w;
  double t_close, t_hold, t_open, t_pause;
  double fill_target, tmax, t_end_hold;
  double r0, rmin, shrink;
  int stop_no_green;  // search speed-up: stop as soon as both start greens are captured
  double jitter;      // start position jitter (px)
  int npos_iter;      // positional solver iterations per step
  // twist: wall slit (LA TRICHEUSE). slit_w <= 0 disables it.
  double slit_ang, slit_w;
} Params;

typedef struct {
  double t_full;      // time the fill target is reached (-1 = never)
  double t_end;       // simulated end
  int hits;           // completed closures
  int empty_hits;     // closures that crushed nothing (must be 0)
  int nballs;
  int crushed_total;
  double green_cap[2];  // capture time of each start green (-1 = never)
  int col_count[NCOL];
  double first_hit;
  double max_overlap;   // max ball-ball overlap measured (px) after solving
  double max_wall_pen;  // max penetration past circle (px)
  int bad_split;        // splits that did not give 2 balls of next colour
  int escapes;          // balls that left through the slit
  double escape_t;      // time of first escape
  int escape_col;
  double fill_at_end;
} Result;

typedef struct { double x, y, vx, vy, r, rt; int col, id, cap, alive, gone; double capa; } Ball;

static Ball B[MAXB];
static int NB, nextid;
static uint64_t rs;
static double rnd(void) {
  rs ^= rs << 13; rs ^= rs >> 7; rs ^= rs << 17;
  return (double)(rs >> 11) * (1.0 / 9007199254740992.0);
}

static Params P;
static Result *RES;
static FILE *fev = NULL, *frec = NULL;
static double T;
// mechanism state
static int phase;  // 0 pause/wait, 1 closing, 2 hold, 3 opening, 4 stopped (open)
static double tp, f, fv;
static int ncap_this;
static int crushed_this;
static int stopped_req;

static void ev(int type, double x, double y, int col, int id, double val) {
  if (!fev) return;
  float rec[6] = {(float)T, (float)type, (float)x, (float)y, (float)col, (float)val};
  fwrite(rec, sizeof(float), 6, fev);
  (void)id;
}

// local frame helpers: a = along motion axis, b = across
static inline void to_ab(double x, double y, double *a, double *b) {
  if (P.axis == 0) { *a = y - P.cy; *b = x - P.cx; } else { *a = x - P.cx; *b = y - P.cy; }
}
static inline void from_ab(double a, double b, double *x, double *y) {
  if (P.axis == 0) { *y = a + P.cy; *x = b + P.cx; } else { *x = a + P.cx; *y = b + P.cy; }
}
static inline void vel_to_ab(double vx, double vy, double *va, double *vb) {
  if (P.axis == 0) { *va = vy; *vb = vx; } else { *va = vx; *vb = vy; }
}
static inline void vel_from_ab(double va, double vb, double *vx, double *vy) {
  if (P.axis == 0) { *vy = va; *vx = vb; } else { *vx = va; *vy = vb; }
}

static void norm_speed(Ball *q) {
  double s = hypot(q->vx, q->vy);
  if (s < 1e-6) { double a = rnd() * 2 * M_PI; q->vx = cos(a); q->vy = sin(a); s = 1; }
  q->vx *= P.speed / s; q->vy *= P.speed / s;
}

static int add_ball(double x, double y, double vx, double vy, double r, int col) {
  if (NB >= MAXB) return -1;
  Ball *q = &B[NB];
  q->x = x; q->y = y; q->vx = vx; q->vy = vy; q->r = r; q->rt = r; q->col = col;
  q->id = nextid++; q->cap = 0; q->alive = 1; q->gone = 0; q->capa = 0;
  norm_speed(q);
  return NB++;
}

// ---- box collision (local frame AABB a0..a1 x b0..b1 moving with velocity va) ----
// returns 1 if contact. limit > 0 caps the positional correction.
static int box_push(Ball *q, double a0, double a1, double b0, double b1, double vbox, double limit) {
  double a, b; to_ab(q->x, q->y, &a, &b);
  double qa = a < a0 ? a0 : (a > a1 ? a1 : a);
  double qb = b < b0 ? b0 : (b > b1 ? b1 : b);
  double da = a - qa, db = b - qb;
  double d2 = da * da + db * db;
  double na, nb, pen;
  if (d2 > q->r * q->r) return 0;
  if (d2 > 1e-12) {
    double d = sqrt(d2); na = da / d; nb = db / d; pen = q->r - d;
  } else {  // centre inside box: least penetration axis
    double p1 = a - a0 + q->r, p2 = a1 - a + q->r, p3 = b - b0 + q->r, p4 = b1 - b + q->r;
    pen = p1; na = -1; nb = 0;
    if (p2 < pen) { pen = p2; na = 1; nb = 0; }
    if (p3 < pen) { pen = p3; na = 0; nb = -1; }
    if (p4 < pen) { pen = p4; na = 0; nb = 1; }
  }
  if (limit > 0 && pen > limit) pen = limit;
  a += na * pen; b += nb * pen;
  from_ab(a, b, &q->x, &q->y);
  double va, vb; vel_to_ab(q->vx, q->vy, &va, &vb);
  double rva = va - vbox * 1.0, rvb = vb;
  double vn = rva * na + rvb * nb;
  if (vn < 0) {
    rva -= 2 * vn * na; rvb -= 2 * vn * nb;
    va = rva + vbox; vb = rvb;
    vel_from_ab(va, vb, &q->vx, &q->vy);
  }
  return 1;
}

static int slit_open_for(Ball *q, double dx, double dy) {
  if (P.slit_w <= 0) return 0;
  double ang = atan2(dy, dx);
  double d = ang - P.slit_ang;
  while (d > M_PI) d -= 2 * M_PI;
  while (d < -M_PI) d += 2 * M_PI;
  double arc = fabs(d) * P.R;  // distance along the rim from slit centre
  // the ball passes only if it fits entirely within the slit
  return (arc + q->r <= P.slit_w * 0.5) ? 1 : 0;
}

static void circle_constrain(Ball *q, int first) {
  if (q->gone) return;
  double dx = q->x - P.cx, dy = q->y - P.cy;
  double d = hypot(dx, dy);
  if (d > P.R - q->r) {
    if (slit_open_for(q, dx, dy)) {
      if (d > P.R + q->r + 2) {  // fully out: gone
        q->gone = 1;
        RES->escapes++;
        if (RES->escape_t < 0) { RES->escape_t = T; RES->escape_col = q->col; }
        ev(6, q->x, q->y, q->col, q->id, 0);
      }
      return;
    }
    // lips of the slit: if ball centre is outside the circle line (passing through), keep it free
    if (d > P.R) return;
    double nx = dx / d, ny = dy / d;
    q->x = P.cx + nx * (P.R - q->r); q->y = P.cy + ny * (P.R - q->r);
    double vn = q->vx * nx + q->vy * ny;
    if (vn > 0) {
      q->vx -= 2 * vn * nx; q->vy -= 2 * vn * ny;
      if (first) ev(3, q->x, q->y, q->col, q->id, 0);
    }
  }
}

static int in_zone(Ball *q) {
  double a, b; to_ab(q->x, q->y, &a, &b);
  return fabs(b) < P.W * 0.5 && fabs(a) < f;
}

static void mech_constrain(Ball *q) {
  if (q->gone) return;
  double hw = P.W * 0.5;
  double lim = (phase == 1 && tp < 0.07) ? 3.0 : 0;
  if (q->cap) {
    // retained inside the closing box
    double a, b; to_ab(q->x, q->y, &a, &b);
    double va, vb; vel_to_ab(q->vx, q->vy, &va, &vb);
    double bl = hw - q->r;
    if (b > bl) { double c = b - bl; if (lim > 0 && c > lim) c = lim; b -= c; if (vb > 0) vb = -vb; }
    if (b < -bl) { double c = -bl - b; if (lim > 0 && c > lim) c = lim; b += c; if (vb < 0) vb = -vb; }
    double al = f - q->r;
    if (al < 0) al = 0;
    if (a > al) { a = al; if (va > fv) va = 2 * fv - va; if (va > 0 && fv >= 0) va = -fabs(va); }
    if (a < -al) { a = -al; if (va < -fv) va = -2 * fv - va; }
    from_ab(a, b, &q->x, &q->y);
    vel_from_ab(va, vb, &q->vx, &q->vy);
    return;
  }
  // free ball vs mechanism solids
  double rodlen = P.R + 40;
  if (phase == 1 || phase == 2 || (phase == 4 && f < 1)) {
    // sealed column (both blocks + the zone between them)
    box_push(q, -(f + P.H), f + P.H, -hw, hw, 0, lim);
  } else {
    box_push(q, f, f + P.H, -hw, hw, fv, 0);
    box_push(q, -(f + P.H), -f, -hw, hw, -fv, 0);
  }
  double rw = P.rod_w * 0.5;
  box_push(q, f + P.H, rodlen, -rw, rw, 0, 0);
  box_push(q, -rodlen, -(f + P.H), -rw, rw, 0, 0);
}

static int overlaps_any(double x, double y, double r, int skip) {
  for (int i = 0; i < NB; i++) {
    if (i == skip || !B[i].alive || B[i].gone) continue;
    double dx = B[i].x - x, dy = B[i].y - y, rr = B[i].r + r + 1.0;
    if (dx * dx + dy * dy < rr * rr) return 1;
  }
  return 0;
}

static int point_ok(double a, double b, double r) {
  double x, y; from_ab(a, b, &x, &y);
  double dx = x - P.cx, dy = y - P.cy;
  if (hypot(dx, dy) > P.R - r - 1) return 0;
  double hw = P.W * 0.5;
  if (fabs(b) < hw + r + 1 && fabs(a) < f + P.H + r + 1) return 0;
  return 1;
}

static void crush(int i) {
  Ball *q = &B[i];
  double a, b; to_ab(q->x, q->y, &a, &b);
  int nc = q->col + 1; if (nc >= NCOL) nc = NCOL - 1;
  double nr = q->r * P.shrink; if (nr < P.rmin) nr = P.rmin;
  q->alive = 0;
  RES->crushed_total++;
  crushed_this++;
  ev(2, q->x, q->y, q->col, q->id, q->r);
  int made = 0;
  double a0 = q->capa * 0.6;
  for (int side = -1; side <= 1; side += 2) {
    double hw = P.W * 0.5;
    double bx = 0, ax = 0; int found = 0;
    for (int k = 0; k < 400 && !found; k++) {
      double bb = side * (hw + nr + 2 + (k / 8) * 6.0);
      double aa = a0 + ((k % 8) - 3.5) * (nr * 0.9) * (1 + (k / 8) * 0.15);
      if (!point_ok(aa, bb, nr)) continue;
      double x, y; from_ab(aa, bb, &x, &y);
      if (overlaps_any(x, y, nr * 0.4, -1)) continue;
      bx = bb; ax = aa; found = 1;
    }
    if (!found) { bx = side * (hw + nr * 0.4 + 2); ax = a0; }
    double th = (rnd() - 0.5) * (M_PI * 0.5);
    double vb = side * cos(th), va = sin(th);
    double x, y, vx, vy; from_ab(ax, bx, &x, &y); vel_from_ab(va, vb, &vx, &vy);
    int k2 = add_ball(x, y, vx, vy, nr, nc);
    if (k2 >= 0) { made++; B[k2].r = nr * 0.4; }
    ev(5, x, y, nc, nextid - 1, nr);
  }
  if (made != 2) RES->bad_split++;
}

static double fill_ratio(void) {
  double s = 0;
  for (int i = 0; i < NB; i++) if (B[i].alive && !B[i].gone) s += B[i].rt * B[i].rt;
  return s / (P.R * P.R);
}

static void compact(void) {
  int j = 0;
  for (int i = 0; i < NB; i++) if (B[i].alive && !(B[i].gone)) B[j++] = B[i];
  // keep escaped balls flying until off-screen (they are kept while gone & on screen)
  NB = j;
}

// grid
#define CS 54.0
#define NG 20
static int head[NG * NG], nxt[MAXB];
static void build_grid(void) {
  for (int k = 0; k < NG * NG; k++) head[k] = -1;
  double x0 = P.cx - P.R - 20, y0 = P.cy - P.R - 20;
  for (int i = 0; i < NB; i++) {
    if (!B[i].alive || B[i].gone) continue;
    int gx = (int)((B[i].x - x0) / CS), gy = (int)((B[i].y - y0) / CS);
    if (gx < 0) gx = 0; if (gx >= NG) gx = NG - 1; if (gy < 0) gy = 0; if (gy >= NG) gy = NG - 1;
    nxt[i] = head[gy * NG + gx]; head[gy * NG + gx] = i;
  }
}

static double solve_pairs(int first, int measure) {
  double x0 = P.cx - P.R - 20, y0 = P.cy - P.R - 20;
  double maxov = 0;
  build_grid();
  for (int i = 0; i < NB; i++) {
    Ball *p = &B[i];
    if (!p->alive || p->gone) continue;
    int gx = (int)((p->x - x0) / CS), gy = (int)((p->y - y0) / CS);
    for (int oy = -1; oy <= 1; oy++) for (int ox = -1; ox <= 1; ox++) {
      int cx = gx + ox, cy = gy + oy;
      if (cx < 0 || cy < 0 || cx >= NG || cy >= NG) continue;
      for (int j = head[cy * NG + cx]; j >= 0; j = nxt[j]) {
        if (j <= i) continue;
        Ball *q = &B[j];
        if (p->cap != q->cap) continue;
        if (measure && p->cap) continue;
        double dx = q->x - p->x, dy = q->y - p->y, rr = p->r + q->r;
        double d2 = dx * dx + dy * dy;
        if (d2 >= rr * rr) continue;
        double d = sqrt(d2);
        double nx, ny;
        if (d < 1e-9) { nx = 1; ny = 0; d = 0; } else { nx = dx / d; ny = dy / d; }
        double ov = rr - d;
        if (measure) { if (ov > maxov) maxov = ov; continue; }
        double m1 = p->r * p->r, m2 = q->r * q->r;
        if (first) {
          double vrel = (q->vx - p->vx) * nx + (q->vy - p->vy) * ny;
          if (vrel < 0) {
            double jimp = 2 * vrel / (1 / m1 + 1 / m2);
            p->vx += jimp / m1 * nx; p->vy += jimp / m1 * ny;
            q->vx -= jimp / m2 * nx; q->vy -= jimp / m2 * ny;
          }
        }
        double w1 = m2 / (m1 + m2), w2 = m1 / (m1 + m2);
        double c = ov;
        p->x -= nx * c * w1; p->y -= ny * c * w1;
        q->x += nx * c * w2; q->y += ny * c * w2;
      }
    }
  }
  return maxov;
}

static void write_frame(void) {
  if (!frec) return;
  int n = 0;
  for (int i = 0; i < NB; i++) if (B[i].alive) n++;
  float hdr[4] = {(float)T, (float)f, (float)phase, (float)n};
  fwrite(hdr, sizeof(float), 4, frec);
  for (int i = 0; i < NB; i++) {
    if (!B[i].alive) continue;
    float rec[6] = {(float)B[i].id, (float)B[i].col, (float)B[i].x, (float)B[i].y, (float)B[i].r, (float)B[i].cap};
    fwrite(rec, sizeof(float), 6, frec);
  }
}

int run(Params *pp, unsigned long long seed, Result *res, const char *rec_path, const char *ev_path) {
  P = *pp; RES = res;
  memset(res, 0, sizeof(Result));
  res->t_full = -1; res->green_cap[0] = res->green_cap[1] = -1; res->first_hit = -1;
  res->escape_t = -1; res->escape_col = -1;
  rs = seed * 0x9E3779B97F4A7C15ULL + 0x2545F4914F6CDD1DULL; if (!rs) rs = 1;
  for (int k = 0; k < 10; k++) rnd();
  fev = ev_path ? fopen(ev_path, "wb") : NULL;
  frec = rec_path ? fopen(rec_path, "wb") : NULL;
  NB = 0; nextid = 0; T = 0;
  phase = 0; tp = 0; f = P.g_open; fv = 0; stopped_req = 0;
  // two greens, one on each side of the mechanism
  for (int s = -1; s <= 1; s += 2) {
    double b = s * (P.W * 0.5 + 0.5 * (P.R - P.W * 0.5)) + (rnd() - 0.5) * P.jitter;
    double a = (rnd() - 0.5) * 2 * P.jitter;
    double x, y; from_ab(a, b, &x, &y);
    double ang = rnd() * 2 * M_PI;
    add_ball(x, y, cos(ang), sin(ang), P.r0, 0);
  }
  int step = 0;
  int rec_every = (int)llround(1.0 / 60.0 / P.dt);
  double t_stop = -1;
  if (frec) write_frame();
  while (1) {
    T += P.dt; step++;
    // ---- mechanism state machine ----
    tp += P.dt;
    double fo = f;
    if (phase == 0) {
      f = P.g_open;
      if (tp >= P.t_pause && !stopped_req) {
        int n = 0;
        for (int i = 0; i < NB; i++) if (B[i].alive && !B[i].gone && in_zone(&B[i])) n++;
        if (n > 0) {
          phase = 1; tp = 0; ncap_this = n; crushed_this = 0;
          for (int i = 0; i < NB; i++) if (B[i].alive && !B[i].gone && in_zone(&B[i])) {
            B[i].cap = 1;
            double a, b; to_ab(B[i].x, B[i].y, &a, &b); B[i].capa = a;
            if (B[i].id < 2 && res->green_cap[B[i].id] < 0) res->green_cap[B[i].id] = T;
          }
          ev(4, 0, 0, 0, 0, n);
        }
      }
      if (stopped_req) phase = 4;
    } else if (phase == 1) {
      double s = tp / P.t_close; if (s > 1) s = 1;
      f = P.g_open * (1 - s * s);
      if (tp >= P.t_close) {
        f = 0; phase = 2; tp = 0;
        res->hits++;
        if (res->first_hit < 0) res->first_hit = T;
        ev(1, 0, 0, 0, 0, crushed_this);
      }
    } else if (phase == 2) {
      f = 0;
      if (tp >= P.t_hold) {
        phase = 3; tp = 0;
        // anything still captured is crushed at the latest here (should not happen)
        for (int i = 0; i < NB; i++) if (B[i].alive && B[i].cap) crush(i);
        if (crushed_this == 0) res->empty_hits++;
        if (stopped_req) { phase = 4; tp = 0; f = 0; }  // circle full: the press stays shut
      }
    } else if (phase == 3) {
      double s = tp / P.t_open; if (s > 1) s = 1;
      f = P.g_open * (s * s * (3 - 2 * s));
      if (tp >= P.t_open) { f = P.g_open; phase = 0; tp = 0; }
    } else { f = (fo < 1) ? 0 : P.g_open; }
    fv = (f - fo) / P.dt;
    // crush captured balls that no longer fit between the faces
    if (phase == 1 || phase == 2) {
      for (int i = 0; i < NB; i++) if (B[i].alive && B[i].cap && f < B[i].r + 0.5) crush(i);
    }
    // ---- integrate ----
    for (int i = 0; i < NB; i++) if (B[i].alive) { B[i].x += B[i].vx * P.dt; B[i].y += B[i].vy * P.dt; }
    // children grow to their full size in ~0.18 s (lets them squeeze into the crowd without overlap)
    for (int i = 0; i < NB; i++) if (B[i].alive && B[i].r < B[i].rt) {
      B[i].r += B[i].rt * 0.6 * P.dt / 0.18; if (B[i].r > B[i].rt) B[i].r = B[i].rt;
    }
    // ---- solve ----
    int nit = P.npos_iter + NB / 25; if (nit > 26) nit = 26;
    for (int it = 0; it < nit; it++) {
      solve_pairs(it == 0, 0);
      for (int i = 0; i < NB; i++) if (B[i].alive) { mech_constrain(&B[i]); circle_constrain(&B[i], it == 0); }
    }
    // stacked captured balls squeezed against a face: crush them
    if (phase == 1) {
      for (int i = 0; i < NB; i++) {
        Ball *p = &B[i];
        if (!p->alive || !p->cap) continue;
        double a, b; to_ab(p->x, p->y, &a, &b);
        if (fabs(a) < f - p->r - 0.5) continue;
        for (int j = 0; j < NB; j++) {
          if (j == i || !B[j].alive || !B[j].cap) continue;
          double dx = B[j].x - p->x, dy = B[j].y - p->y, rr = p->r + B[j].r;
          if (dx * dx + dy * dy < (rr - 0.3 * p->r) * (rr - 0.3 * p->r)) { crush(i); break; }
        }
      }
    }
    for (int i = 0; i < NB; i++) if (B[i].alive) norm_speed(&B[i]);
    // escaped balls: remove once off-screen
    for (int i = 0; i < NB; i++) if (B[i].alive && B[i].gone) {
      if (B[i].x < -60 || B[i].x > 1140 || B[i].y < -60 || B[i].y > 1980) B[i].alive = 0;
    }
    if (step % 8 == 0) {
      // keep arrays compact (only dead balls removed; escaped ones stay alive while on screen)
      int j = 0;
      for (int i = 0; i < NB; i++) if (B[i].alive) B[j++] = B[i];
      NB = j;
    }
    // ---- fill ----
    if (res->t_full < 0 && fill_ratio() >= P.fill_target) {
      res->t_full = T; stopped_req = 1;
      t_stop = T + P.t_end_hold;
    }
    if (phase == 0 && stopped_req) phase = 4;
    if (P.stop_no_green && res->green_cap[0] >= 0 && res->green_cap[1] >= 0 && !frec) break;
    if (frec && step % rec_every == 0) write_frame();
    if (step % rec_every == 0 && (frec || T > 20)) {
      double ov = solve_pairs(0, 1);
      if (ov > res->max_overlap) res->max_overlap = ov;
      for (int i = 0; i < NB; i++) if (B[i].alive && !B[i].gone) {
        double d = hypot(B[i].x - P.cx, B[i].y - P.cy) + B[i].r - P.R;
        if (d > res->max_wall_pen && !slit_open_for(&B[i], B[i].x - P.cx, B[i].y - P.cy)) res->max_wall_pen = d;
      }
    }
    if (t_stop > 0 && T >= t_stop - 1e-9) break;
    if (T > P.tmax) break;
  }
  res->t_end = T;
  for (int i = 0; i < NB; i++) if (B[i].alive && !B[i].gone) { res->nballs++; res->col_count[B[i].col]++; }
  res->fill_at_end = fill_ratio();
  if (fev) fclose(fev);
  if (frec) fclose(frec);
  fev = frec = NULL;
  (void)compact;
  return 0;
}
