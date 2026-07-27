// eyes.h - Geedo's idle face: two rounded rectangles that wander and blink.
//
// Drawn in code rather than stored as frames. A wandering idle needs dozens of
// gaze positions, and every stored position would cost 1 KB of RAM we do not
// have (see FIRMWARE.md - the animation library already exceeds free RAM).
// Generated frames cost ~30 bytes of state and never repeat.
//
// Output is a 1024-byte SSD1306 page buffer - the same GDA1 frame format the
// animation player and the kaomoji pack use, so it goes through drawFrame()
// unchanged.
#pragma once
#include <stdint.h>
#include <string.h>

// Shape, chosen against renders of the real thing.
#define EYE_W 30
#define EYE_H 42
#define EYE_R 7
#define EYE_GAP_BLACK 18                       // black pixels between the eyes
#define EYE_CX_L (64 - (EYE_W + EYE_GAP_BLACK) / 2)
#define EYE_CX_R (64 + (EYE_W + EYE_GAP_BLACK) / 2)
#define EYE_CY 32

// How far the gaze roams. 30x42 centred leaves 11 px above and below, so 5 is
// the most we can travel vertically and still keep the eye on screen.
#define EYE_WANDER_X 8
#define EYE_WANDER_Y 5

#define EYES_FRAME_MS 120                      // one held frame (micro-tremor)
#define EYES_BLINK_MS 45                       // one blink frame - fast
#define EYES_BLINK_MIN_MS 3000
#define EYES_BLINK_SPAN_MS 3000

// A blink squashes the eye instead of drawing a lid: cheap, and it is the same
// trick the hand-drawn blink_eyes animation uses.
#define EYES_BLINK_STEPS 3
static const uint8_t EYES_BLINK_SQUASH[EYES_BLINK_STEPS] = {45, 12, 45};

static inline void eyes_px_(uint8_t* fb, int x, int y) {
  if (x < 0 || x > 127 || y < 0 || y > 63) return;
  fb[(y >> 3) * 128 + x] |= (uint8_t)(1u << (y & 7));
}

// Filled rounded rectangle, centred. The corner test is the squared distance
// to the inset rectangle, which traces a true arc rather than the stair-step
// a quarter-circle blit leaves behind.
static inline void eyes_roundrect_(uint8_t* fb, int cx, int cy, int w, int h, int r) {
  int x0 = cx - w / 2, x1 = x0 + w - 1;
  int y0 = cy - h / 2, y1 = y0 + h - 1;
  if (r > w / 2) r = w / 2;
  if (r > h / 2) r = h / 2;
  int ix0 = x0 + r, ix1 = x1 - r, iy0 = y0 + r, iy1 = y1 - r;
  // Distance to the inset rect, as max(lo - p, p - hi, 0). On a heavily
  // squashed eye the inset inverts (iy0 > iy1) and both terms can be
  // positive, so this has to be a real three-way max - testing them in
  // sequence silently returns 0 and fattens the blink frames.
  for (int y = y0; y <= y1; y++) {
    for (int x = x0; x <= x1; x++) {
      int dx = ix0 - x, ex = x - ix1;
      if (ex > dx) dx = ex;
      if (dx < 0) dx = 0;
      int dy = iy0 - y, ey = y - iy1;
      if (ey > dy) dy = ey;
      if (dy < 0) dy = 0;
      if (dx * dx + dy * dy <= r * r) eyes_px_(fb, x, y);
    }
  }
}

// Both eyes at gaze offset (dx, dy), squashed to `squash` percent of full
// height. Always moves together - split gaze reads as broken, not alive.
static inline void eyes_render(int dx, int dy, uint8_t squash, uint8_t* frame1024) {
  memset(frame1024, 0, 1024);
  int h = (EYE_H * (int)squash) / 100;
  if (h < 2) h = 2;
  eyes_roundrect_(frame1024, EYE_CX_L + dx, EYE_CY + dy, EYE_W, h, EYE_R);
  eyes_roundrect_(frame1024, EYE_CX_R + dx, EYE_CY + dy, EYE_W, h, EYE_R);
}

typedef struct {
  int tx, ty;              // where he is currently looking
  uint32_t hold_ms, held;  // how long to stay there, how long he has
  uint32_t since_blink, blink_at;
  uint8_t blink_step;      // 0 = eyes open
} EyeState;

static inline void eyes_init(EyeState* s) {
  memset(s, 0, sizeof(*s));
  s->hold_ms = 800;
  s->blink_at = EYES_BLINK_MIN_MS;
}

// Renders the next frame and returns how long to hold it. `rnd` is one fresh
// random word per call (esp_random() on device); `mood` is 40..100 and makes a
// happy Geedo dart about while a content one drifts.
//
// The eyes SNAP between positions - never tweened. Smooth sliding is what
// makes robot eyes look sedated; real gaze jumps in ~30 ms and then holds.
static inline uint16_t eyes_next(EyeState* s, uint8_t mood, uint32_t rnd,
                                 uint8_t* frame) {
  if (s->blink_step > 0) {                     // playing out a blink
    uint8_t sq = EYES_BLINK_SQUASH[s->blink_step - 1];
    s->blink_step = (s->blink_step >= EYES_BLINK_STEPS) ? 0 : s->blink_step + 1;
    eyes_render(s->tx, s->ty, sq, frame);
    return EYES_BLINK_MS;
  }

  s->held += EYES_FRAME_MS;
  s->since_blink += EYES_FRAME_MS;

  if (s->since_blink >= s->blink_at) {         // start a blink
    s->since_blink = 0;
    s->blink_at = EYES_BLINK_MIN_MS + (rnd % EYES_BLINK_SPAN_MS);
    s->blink_step = 2;                         // frame 1 is drawn right now
    eyes_render(s->tx, s->ty, EYES_BLINK_SQUASH[0], frame);
    return EYES_BLINK_MS;
  }

  if (s->held >= s->hold_ms) {                 // saccade somewhere new
    s->held = 0;
    // Averaging two draws biases toward the centre, so short hops are common
    // and a big look to the corner is an event.
    int ax = (int)(rnd % (2 * EYE_WANDER_X + 1)) - EYE_WANDER_X;
    int bx = (int)((rnd >> 8) % (2 * EYE_WANDER_X + 1)) - EYE_WANDER_X;
    int ay = (int)((rnd >> 16) % (2 * EYE_WANDER_Y + 1)) - EYE_WANDER_Y;
    int by = (int)((rnd >> 24) % (2 * EYE_WANDER_Y + 1)) - EYE_WANDER_Y;
    s->tx = (ax + bx) / 2;
    s->ty = (ay + by) / 2;
    uint32_t base = (mood >= 85) ? 300u : (mood >= 65 ? 450u : 700u);
    uint32_t span = (mood >= 85) ? 900u : (mood >= 65 ? 1400u : 1900u);
    s->hold_ms = base + (rnd % span);
    eyes_render(s->tx, s->ty, 100, frame);
    return EYES_FRAME_MS;
  }

  // Holding. A pixel of tremor keeps him from looking switched off.
  int jx = (int)(rnd & 3u) - 1; if (jx > 1) jx = 1;
  int jy = (int)((rnd >> 2) & 3u) - 1; if (jy > 1) jy = 1;
  eyes_render(s->tx + jx, s->ty + jy, 100, frame);
  return EYES_FRAME_MS;
}

// Wide-eyed delight, for when he has just been petted.
static inline void eyes_happy(uint8_t* frame) { eyes_render(0, -2, 100, frame); }
