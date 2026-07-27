/*
  Geedo Cloud Prototype
  ESP32 + SSD1306 + WiFiManager (no creds in code).

  FIRST BOOT:
    - OLED shows "Connect to: GEEDO-Setup"
    - On your phone, connect to that WiFi (no password)
    - A page pops up. Pick your home WiFi, enter password.
    - ESP saves it forever in its own flash.

  AFTER THAT:
    - Auto-connects to remembered WiFi every boot.
    - Polls Hub for new animations every POLL_INTERVAL_MS.

  THE BUTTON (SW1, on the outside of Geedo):
    - Tap          -> pet him. He reacts, and his mood goes up.
    - Hold 5 s     -> erase saved WiFi and reopen the setup portal
                      (a countdown shows on screen; let go to cancel)

  MOOD: one number, 40..100, kept in LittleFS. Petting raises it, time lowers
  it back to 40 and no further - Geedo can be delighted or plain content, but
  never sad at his owner. Mood picks which family of faces he pulls.

  WIRING (shipping ESP32-C3 board - see hardware/README.md):
    OLED  VCC -> 3.3V, GND -> GND, SDA -> GPIO4, SCL -> GPIO5
    SW1 MAIN  -> GPIO3 to GND     SW2 BOOT -> GPIO9 to GND
    SW3 RESET -> EN to GND (hardware reset, firmware never sees it)
  On a classic ESP32 devkit the pin map falls back to SDA 21 / SCL 22 and
  the devkit's BOOT button stands in for SW1.
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <Update.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ArduinoJson.h>
#include <WiFiManager.h>
#include <LittleFS.h>
#include "boot_anim_progmem.h"
#include "kamoji.h"
#include "eyes.h"

// ================== CONFIG (no secrets) ==================
const uint32_t FIRMWARE_VERSION = 12;
const char* HUB = "https://breadboardy.github.io/Geedo-Hub";
// const char* HUB = "https://breadboard.github.io/Geedo-Hub";  // production

// Pin map. The shipping Geedo is an ESP32-C3 (see hardware/README.md);
// bring-up happens on a classic ESP32 devkit, so both are covered here and
// the right set is chosen at compile time.
#if CONFIG_IDF_TARGET_ESP32C3
  #define SDA_PIN 4
  #define SCL_PIN 5
  #define MAIN_BTN_PIN 3      // SW1, the button on the outside of Geedo
  #define BOOT_BTN_PIN 9      // SW2, internal
#else
  #define SDA_PIN 21
  #define SCL_PIN 22
  #define MAIN_BTN_PIN 0      // devkit's BOOT button stands in for SW1
  #define BOOT_BTN_PIN 0
#endif
// SW3 pulls EN low: a hardware reset, invisible to firmware.

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_ADDR 0x3C

const uint32_t POLL_INTERVAL_MS = 60UL * 1000UL;
const uint32_t PLAY_TIME_MS = 5000;
const uint32_t IDLE_EYES_MS = 9000;   // wandering between each animation
const uint8_t  KAOMOJI_CHANCE_PCT = 40;   // odds of a face appearing between animations
const uint32_t KAOMOJI_TIME_MS = 2000;    // how long each face stays up
const uint32_t WIFI_RESET_HOLD_MS = 5000; // hold MAIN this long to erase WiFi
const uint32_t BTN_TAP_MS = 700;          // shorter than this is a tap, not a hold

// Mood. Petting lifts it; it drifts back down to MOOD_FLOOR and stops there,
// so Geedo can be delighted or plain content but never miserable.
const uint8_t  MOOD_FLOOR = 40;
const uint8_t  MOOD_MAX = 100;
const uint8_t  MOOD_PET_BOOST = 8;
const uint32_t MOOD_DECAY_MS = 15UL * 60UL * 1000UL;   // -1 every 15 min
const uint32_t MOOD_SAVE_MS = 10UL * 60UL * 1000UL;    // flash-wear throttle
const uint32_t PET_STREAK_MS = 2000;      // pets this close together stack

#define AP_NAME "GEEDO-Setup"
// =========================================================

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

struct Anim {
  String id, name, file, hash;
  uint16_t size;
  uint8_t frame_count, fps, flags;
  uint8_t* durations;
  uint8_t* pixels;
};

static const uint8_t MAX_ANIMS = 40;
Anim anims[MAX_ANIMS];
uint8_t anim_count = 0;
uint32_t lastPoll = 0;

// Forward declarations (LittleFS cache helpers defined later)
extern bool fsReady;
String cachePath(const String& id);
String cacheHashPath(const String& id);
bool readCachedHash(const String& id, String& outHash);
bool readCacheBin(const String& id, uint8_t** outBuf, size_t* outLen);
bool writeCache(const String& id, const String& hash, const uint8_t* buf, size_t len);
bool parseAnimBin(const uint8_t* bb, size_t bl, const String& id, const String& name,
                  const String& file, const String& hash, uint16_t size);
int findAnim(const char* id);
void petGeedo();
void showMoodKaomoji(uint32_t ms);
void saveMood(bool force = false);

void freeAnims() {
  for (uint8_t i = 0; i < anim_count; i++) {
    if (anims[i].durations) { free(anims[i].durations); anims[i].durations = nullptr; }
    if (anims[i].pixels)    { free(anims[i].pixels);    anims[i].pixels = nullptr; }
  }
  anim_count = 0;
}

void showStatus(const char* line1, const char* line2 = nullptr, const char* line3 = nullptr) {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println(line1);
  if (line2) display.println(line2);
  if (line3) display.println(line3);
  display.display();
}

void showSetupScreen() {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println(F("FIRST-TIME SETUP"));
  display.println();
  display.println(F("On your phone,"));
  display.println(F("connect to WiFi:"));
  display.setTextSize(1);
  display.println();
  display.println(F("> " AP_NAME));
  display.println(F("(no password)"));
  display.display();
}

// ===== MAIN button: tap = pet him, hold 5 s = erase WiFi and set up again =====
// SW1 shorts GPIO3 to GND, so the pin idles high and reads LOW when pressed.
bool btnDown() { return digitalRead(MAIN_BTN_PIN) == LOW; }

// Set while Geedo is mid-reaction, so the button poll inside idleDelay()
// cannot re-enter petGeedo() from within petGeedo()'s own face.
bool reacting = false;

void eraseWiFiAndRestart() {
  showStatus("WIFI ERASED", "restarting...", "set up on your phone");
  saveMood(true);          // losing the WiFi should not lose how he feels
  WiFiManager wm;
  wm.resetSettings();
  delay(1500);
  ESP.restart();
}

// Runs while the button is held. A quick tap returns immediately (the caller
// treats that as "skip"); holding past WIFI_RESET_HOLD_MS wipes the WiFi
// credentials. Letting go early cancels, so it cannot fire by accident.
void serviceButtonHold() {
  uint32_t t0 = millis();
  bool warned = false;
  while (btnDown()) {
    uint32_t held = millis() - t0;
    if (held >= WIFI_RESET_HOLD_MS) { eraseWiFiAndRestart(); return; }
    if (held > BTN_TAP_MS) {
      char l2[24];
      snprintf(l2, sizeof(l2), "erasing WiFi in %lu",
               (unsigned long)((WIFI_RESET_HOLD_MS - held + 999) / 1000));
      showStatus("KEEP HOLDING", l2, "let go to cancel");
      warned = true;
    }
    delay(40);
  }
  if (warned) { showStatus("cancelled", "WiFi kept"); return; }
  petGeedo();   // a plain tap is a pet
}

// delay() that stays awake to the button. Returns true if the caller should
// cut whatever it is showing short.
bool idleDelay(uint32_t ms) {
  uint32_t t0 = millis();
  while ((millis() - t0) < ms) {
    if (!reacting && btnDown()) { serviceButtonHold(); return true; }
    delay(5);
  }
  return false;
}

bool httpGet(const String& url, uint8_t** outBuf, size_t* outLen) {
  HTTPClient http;
  WiFiClientSecure secClient;
  secClient.setInsecure();
  Serial.printf("GET %s\n", url.c_str());
  http.begin(secClient, url);
  int code = http.GET();
  if (code != 200) { Serial.printf("HTTP %d\n", code); http.end(); return false; }
  int len = http.getSize();
  if (len <= 0) { http.end(); return false; }
  uint8_t* buf = (uint8_t*)malloc(len);
  if (!buf) { http.end(); return false; }
  WiFiClient* stream = http.getStreamPtr();
  size_t got = 0;
  uint32_t start = millis();
  while (got < (size_t)len && (millis() - start < 15000)) {
    if (stream->available()) got += stream->read(buf + got, len - got);
    else delay(2);
  }
  http.end();
  if (got != (size_t)len) { free(buf); return false; }
  *outBuf = buf; *outLen = got;
  return true;
}

bool loadManifestAndAnims() {
  uint8_t* buf; size_t len;
  if (!httpGet(String(HUB) + "/animations/manifest.json", &buf, &len)) return false;
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, buf, len);
  free(buf);
  if (err) { Serial.printf("JSON err: %s\n", err.c_str()); return false; }

  freeAnims();
  JsonArray arr = doc["animations"].as<JsonArray>();
  uint8_t hit = 0, miss = 0;
  for (JsonObject a : arr) {
    if (anim_count >= MAX_ANIMS) break;
    String id   = a["id"]   | "";
    String name = a["name"] | "";
    String file = a["file"] | "";
    String hash = a["hash"] | "";
    uint16_t sz = a["size"] | 0;

    // CACHE HIT? Check stored hash against manifest hash.
    String cachedHash;
    if (readCachedHash(id, cachedHash) && cachedHash == hash) {
      uint8_t* cb; size_t cl;
      if (readCacheBin(id, &cb, &cl)) {
        if (parseAnimBin(cb, cl, id, name, file, hash, sz)) {
          free(cb); hit++;
          Serial.printf("cache HIT %s\n", id.c_str());
          continue;
        }
        free(cb);
      }
    }

    // CACHE MISS: download
    uint8_t* bb; size_t bl;
    String url = String(HUB) + "/animations/" + file;
    if (!httpGet(url, &bb, &bl)) { Serial.printf("Failed %s\n", file.c_str()); continue; }
    if (!parseAnimBin(bb, bl, id, name, file, hash, sz)) { Serial.println("parse fail"); free(bb); continue; }
    writeCache(id, hash, bb, bl);  // persist for next boot
    free(bb);
    miss++;
    Serial.printf("Loaded %s (%d frames)\n", id.c_str(), anims[anim_count-1].frame_count);
  }

  // Prune cached entries no longer in manifest
  if (fsReady) {
    File dir = LittleFS.open("/a");
    if (dir && dir.isDirectory()) {
      File f = dir.openNextFile();
      while (f) {
        String fname = f.name();
        f.close();
        if (fname.endsWith(".bin")) {
          String id = fname.substring(0, fname.length() - 4);
          if (findAnim(id.c_str()) < 0) {
            LittleFS.remove(cachePath(id));
            LittleFS.remove(cacheHashPath(id));
            Serial.printf("pruned cache %s\n", id.c_str());
          }
        }
        f = dir.openNextFile();
      }
    }
  }

  Serial.printf("Manifest: %u cached, %u downloaded\n", hit, miss);
  return anim_count > 0;
}

void drawFrame(const uint8_t* frame) {
  uint8_t* buf = display.getBuffer();
  memcpy(buf, frame, 1024);
  display.display();
}

void playAnim(const Anim& A, uint32_t maxMs) {
  bool loop = A.flags & 1;
  bool pp   = A.flags & 2;
  int dir = 1, i = 0;
  uint32_t start = millis();
  while (millis() - start < maxMs) {
    drawFrame(A.pixels + i * 1024);
    if (idleDelay(1000 / max((uint8_t)1, A.fps) * A.durations[i])) return;
    i += dir;
    if (i >= A.frame_count) {
      if (pp) { dir = -1; i = A.frame_count - 2; }
      else if (loop) i = 0;
      else return;
    } else if (i < 0) {
      if (pp) { dir = 1; i = 1; }
      else if (loop) i = A.frame_count - 1;
      else return;
    }
  }
}



int findAnim(const char* id) {
  for (uint8_t i = 0; i < anim_count; i++) {
    if (anims[i].id == id) return i;
  }
  return -1;
}

void playAnimOnce(const Anim& A) {
  uint16_t basePer = 1000 / max((uint8_t)1, A.fps);
  for (uint8_t f = 0; f < A.frame_count; f++) {
    drawFrame(A.pixels + (size_t)f * 1024);
    if (idleDelay(basePer * (A.durations[f] ? A.durations[f] : 1))) return;
  }
}

void playSystemAnim(const char* id, uint8_t repeats = 1) {
  int idx = findAnim(id);
  if (idx < 0) { Serial.printf("sys anim missing: %s\n", id); return; }
  for (uint8_t r = 0; r < repeats; r++) playAnimOnce(anims[idx]);
}


bool isSystemAnim(const Anim& A) {
  return A.id.startsWith("animations_boot_");
}

// ===== kaomoji faces (kamoji.h - 191 of them, always available, no WiFi needed) =====
void showKaomoji(uint16_t id, uint32_t ms) {
  uint8_t frame[1024];
  kaomoji_show(id, frame);           // renders a GDA1-format page buffer
  drawFrame(frame);                  // same blit path as animations
  Serial.printf("kaomoji %u: %s\n", id, kaomoji_face(id % KAOMOJI_COUNT));
  idleDelay(ms);
}

void showRandomKaomoji(uint32_t ms) {
  showKaomoji(esp_random() % KAOMOJI_COUNT, ms);
}

uint8_t kaomojiCat(const char* name) {
  for (uint8_t i = 0; i < KAOMOJI_CATEGORY_COUNT; i++)
    if (!strcmp((const char*)pgm_read_ptr(&KAOMOJI_CATEGORY_NAMES[i]), name)) return i;
  return 255;
}

// random face from one category ("happy", "sad", "robot", ...)
void showRandomKaomojiFrom(const char* cat, uint32_t ms) {
  uint8_t c = kaomojiCat(cat);
  uint16_t n = 0;
  for (uint16_t i = 0; i < KAOMOJI_COUNT; i++)
    if (kaomoji_category(i) == c) n++;
  if (n == 0) { showRandomKaomoji(ms); return; }
  uint16_t k = esp_random() % n;
  for (uint16_t i = 0; i < KAOMOJI_COUNT; i++)
    if (kaomoji_category(i) == c && k-- == 0) { showKaomoji(i, ms); return; }
}

// ===== mood =====
// One number, 40..100. Petting pushes it up, time pulls it back down to the
// floor and no further: a neglected Geedo goes back to plain content, never
// sad. It survives a power cut in LittleFS.
uint8_t  mood = 60;
uint32_t lastDecayAt = 0;
uint32_t lastSaveAt = 0;
uint32_t lastPetAt = 0;
uint8_t  petStreak = 0;
bool     moodDirty = false;

void loadMood() {
  if (!fsReady) return;
  File f = LittleFS.open("/mood", "r");
  if (!f) return;
  long v = f.parseInt();
  f.close();
  if (v >= MOOD_FLOOR && v <= MOOD_MAX) mood = (uint8_t)v;
  Serial.printf("mood restored: %u\n", mood);
}

void saveMood(bool force) {
  if (!fsReady || !moodDirty) return;
  if (!force && (millis() - lastSaveAt) < MOOD_SAVE_MS) return;
  File f = LittleFS.open("/mood", "w");
  if (!f) return;
  f.print(mood);
  f.close();
  lastSaveAt = millis();
  moodDirty = false;
}

// call often; unsigned subtraction makes the millis() rollover a non-event
void decayMood() {
  if ((millis() - lastDecayAt) < MOOD_DECAY_MS) return;
  lastDecayAt = millis();
  if (mood > MOOD_FLOOR) { mood--; moodDirty = true; }
}

// Which family of faces suits him right now. Nothing below content is ever
// reachable from mood alone.
const char* moodCategory() {
  if (mood >= 85) return "love";
  if (mood >= 65) return "happy";
  static const char* const calm[] = {"happy", "cool", "animal", "robot"};
  return calm[esp_random() % 4];
}

void showMoodKaomoji(uint32_t ms) { showRandomKaomojiFrom(moodCategory(), ms); }

// ===== idle: wandering eyes =====
// This is Geedo's resting state. Animations become things he does now and
// then; the eyes are what he looks like the rest of the time.
EyeState eyeState;

void idleEyes(uint32_t ms) {
  uint8_t frame[1024];
  uint32_t t0 = millis();
  while ((millis() - t0) < ms) {
    uint16_t hold = eyes_next(&eyeState, mood, esp_random(), frame);
    drawFrame(frame);
    if (idleDelay(hold)) return;      // petted mid-wander: go and react
  }
}

void petGeedo() {
  uint32_t now = millis();
  petStreak = (now - lastPetAt < PET_STREAK_MS && petStreak < 200)
              ? petStreak + 1 : 1;
  lastPetAt = now;
  mood = (mood > MOOD_MAX - MOOD_PET_BOOST) ? MOOD_MAX : mood + MOOD_PET_BOOST;
  moodDirty = true;
  Serial.printf("pet! streak %u, mood %u\n", petStreak, mood);

  reacting = true;                      // stop the reaction re-triggering itself
  uint8_t frame[1024];
  eyes_happy(frame);                    // eyes perk up first - instant feedback
  drawFrame(frame);
  delay(150);
  if (petStreak >= 5)      showRandomKaomojiFrom("surprised", 700);
  else if (petStreak >= 3) showRandomKaomojiFrom("love", 800);
  else                     showRandomKaomojiFrom(mood >= 85 ? "love" : "happy", 800);
  reacting = false;
}

bool checkFirmwareUpdate() {
  WiFiClientSecure sec;
  sec.setInsecure();
  HTTPClient http;
  // ?t= makes every poll a fresh CDN cache key - GitHub Pages otherwise
  // serves a cached manifest for up to 10 minutes after a deploy
  http.begin(sec, String(HUB) + "/firmware/manifest.json?t=" + String(millis()));
  int code = http.GET();
  if (code != 200) { Serial.printf("OTA manifest HTTP %d\n", code); http.end(); return false; }
  String body = http.getString();
  http.end();

  JsonDocument doc;
  if (deserializeJson(doc, body)) { Serial.println("OTA bad json"); return false; }
  uint32_t latest = doc["version"] | 0;
  Serial.printf("OTA: current=%u remote=%u\n", FIRMWARE_VERSION, latest);
  if (latest <= FIRMWARE_VERSION) return false;

  const char* binPath = doc["url"] | (const char*)nullptr;
  if (!binPath) return false;
  String binUrl = String(HUB) + "/" + binPath;
  Serial.printf("OTA: downloading %s\n", binUrl.c_str());

  playSystemAnim("animations_boot_update_animation");
  showStatus("UPDATING", ("v" + String(latest)).c_str(), "DO NOT UNPLUG");
  http.begin(sec, binUrl);
  code = http.GET();
  if (code != 200) { http.end(); return false; }
  int len = http.getSize();
  if (len <= 0) { http.end(); return false; }

  if (!Update.begin(len)) { Serial.println("Update.begin fail"); http.end(); return false; }
  showStatus("UPDATING", ("v" + String(latest)).c_str(), "DO NOT UNPLUG");
  size_t written = Update.writeStream(*http.getStreamPtr());
  http.end();
  if (written != (size_t)len) { Update.abort(); return false; }
  if (!Update.end(true)) { Serial.println("Update.end fail"); return false; }

  showStatus("UPDATE OK", "rebooting...");
  saveMood(true);          // an update should not reset his mood either
  delay(1500);
  ESP.restart();
  return true;
}

// ===== INSTANT BOOT: play PROGMEM boot animation before WiFi =====
void playBootAnimProgmem() {
  // Layout matches .geedo.bin: durations[frame_count], then frames * 1024
  const uint8_t* durations = BOOT_ANIM_DATA + 8;
  const uint8_t* frames    = BOOT_ANIM_DATA + 8 + BOOT_ANIM_FRAME_COUNT;
  uint16_t basePer = 1000 / max((uint8_t)1, BOOT_ANIM_FPS);
  uint8_t buf[1024];
  for (uint8_t f = 0; f < BOOT_ANIM_FRAME_COUNT; f++) {
    memcpy_P(buf, frames + (size_t)f * 1024, 1024);  // copy from flash to RAM
    memcpy(display.getBuffer(), buf, 1024);
    display.display();
    uint8_t d = pgm_read_byte(durations + f);
    delay(basePer * (d ? d : 1));
  }
}

// ===== LittleFS cache =====
bool fsReady = false;

void mountFS() {
  fsReady = LittleFS.begin(true);  // true = format on first mount failure
  Serial.printf("LittleFS: %s\n", fsReady ? "ok" : "FAIL");
}

String cachePath(const String& id)     { return "/a/" + id + ".bin"; }
String cacheHashPath(const String& id) { return "/a/" + id + ".h"; }

bool readCachedHash(const String& id, String& outHash) {
  if (!fsReady) return false;
  File f = LittleFS.open(cacheHashPath(id), "r");
  if (!f) return false;
  outHash = f.readString();
  f.close();
  return outHash.length() > 0;
}

bool writeCache(const String& id, const String& hash, const uint8_t* buf, size_t len) {
  if (!fsReady) return false;
  LittleFS.mkdir("/a");
  File f = LittleFS.open(cachePath(id), "w");
  if (!f) { Serial.printf("cache write fail %s\n", id.c_str()); return false; }
  size_t w = f.write(buf, len);
  f.close();
  if (w != len) { LittleFS.remove(cachePath(id)); return false; }
  File hf = LittleFS.open(cacheHashPath(id), "w");
  if (hf) { hf.print(hash); hf.close(); }
  Serial.printf("cached %s (%u B)\n", id.c_str(), (unsigned)len);
  return true;
}

bool readCacheBin(const String& id, uint8_t** outBuf, size_t* outLen) {
  if (!fsReady) return false;
  File f = LittleFS.open(cachePath(id), "r");
  if (!f) return false;
  size_t len = f.size();
  uint8_t* buf = (uint8_t*)malloc(len);
  if (!buf) { f.close(); return false; }
  size_t r = f.read(buf, len);
  f.close();
  if (r != len) { free(buf); return false; }
  *outBuf = buf; *outLen = len;
  return true;
}

// Parse a .geedo.bin blob into anims[anim_count]. Returns true on ok.
bool parseAnimBin(const uint8_t* bb, size_t bl, const String& id, const String& name,
                  const String& file, const String& hash, uint16_t size) {
  if (bl < 8 || memcmp(bb, "GDA1", 4) != 0) return false;
  if (anim_count >= MAX_ANIMS) return false;
  Anim& A = anims[anim_count];
  A.id = id; A.name = name; A.file = file; A.hash = hash; A.size = size;
  A.frame_count = bb[5]; A.fps = bb[6]; A.flags = bb[7];
  A.durations = (uint8_t*)malloc(A.frame_count);
  if (!A.durations) return false;
  memcpy(A.durations, bb + 8, A.frame_count);
  size_t pix_len = (size_t)A.frame_count * 1024;
  A.pixels = (uint8_t*)malloc(pix_len);
  if (!A.pixels) { free(A.durations); A.durations = nullptr; return false; }
  memcpy(A.pixels, bb + 8 + A.frame_count, pix_len);
  anim_count++;
  return true;
}

// Load any cached anims into RAM (called BEFORE WiFi so Geedo is alive offline)
uint8_t loadCachedAnims() {
  if (!fsReady) return 0;
  File dir = LittleFS.open("/a");
  if (!dir || !dir.isDirectory()) return 0;
  uint8_t loaded = 0;
  File f = dir.openNextFile();
  while (f) {
    String fname = f.name();  // e.g. "blink_eyes.bin"
    if (fname.endsWith(".bin")) {
      String id = fname.substring(0, fname.length() - 4);
      size_t len = f.size();
      uint8_t* buf = (uint8_t*)malloc(len);
      if (buf && f.read(buf, len) == len) {
        String hash; readCachedHash(id, hash);
        if (parseAnimBin(buf, len, id, id, id + ".bin", hash, len)) loaded++;
      }
      if (buf) free(buf);
    }
    f.close();
    f = dir.openNextFile();
  }
  Serial.printf("LittleFS: loaded %u cached anims\n", loaded);
  return loaded;
}

void setup() {
  Serial.begin(115200);
  delay(200);

  pinMode(MAIN_BTN_PIN, INPUT_PULLUP);

  Wire.begin(SDA_PIN, SCL_PIN);
  // A loose OLED ribbon used to hang here forever. Retry, then carry on
  // regardless: without WiFi we could never ship a fix, and a Geedo that
  // still reaches the Hub can be repaired by an update.
  bool displayOK = false;
  for (uint8_t attempt = 0; attempt < 3 && !displayOK; attempt++) {
    displayOK = display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR);
    if (!displayOK) { Serial.println("OLED init failed, retrying"); delay(300); }
  }
  if (!displayOK) Serial.println("OLED not responding - continuing headless");
  display.clearDisplay();
  display.display();

  // ⚡ INSTANT: play boot anim from flash before anything else
  playBootAnimProgmem();

  // 💾 Mount LittleFS and load any cached anims into RAM
  mountFS();
  loadMood();
  eyes_init(&eyeState);
  lastDecayAt = millis();
  uint8_t cached = loadCachedAnims();
  if (cached > 0) {
    // We have stuff to show even without WiFi — kick off one loop pass
    for (uint8_t i = 0; i < anim_count && i < 2; i++) {
      if (!isSystemAnim(anims[i])) { playAnim(anims[i], 1500); break; }
    }
  }

  // WiFiManager handles everything: tries saved creds, else opens portal
  WiFiManager wm;
  wm.setConfigPortalTimeout(300);  // 5 min portal timeout

  // Show setup screen if no saved creds yet
  if (WiFi.SSID().length() == 0) {
    showSetupScreen();
  } else {
    showStatus("Connecting WiFi", WiFi.SSID().c_str());
  }

  bool ok = wm.autoConnect(AP_NAME);
  if (!ok) {
    // OFFLINE MODE: no WiFi, but cached anims keep Geedo alive
    playSystemAnim("animations_boot_failed_to_connect");
    if (anim_count == 0) {
      showStatus("No WiFi", "and no cache", "hold button 5s");
    }
    lastPoll = millis();
    return;
  }

  showStatus("WiFi OK", WiFi.localIP().toString().c_str());
  delay(600);
  showStatus("Checking", "firmware...");
  checkFirmwareUpdate();
  delay(400);

  showStatus("Fetching", "manifest...");
  if (!loadManifestAndAnims()) {
    if (anim_count == 0) {
      playSystemAnim("animations_boot_error_blue_screen_of_death", 2);
      showStatus("Fetch FAILED", "check HUB");
    }
  } else {
    playSystemAnim("animations_boot_turning_on");
    showMoodKaomoji(1500);   // hello, in whatever mood he woke up in
    idleEyes(2500);          // then he opens his eyes and looks around
  }
  lastPoll = millis();
}

void loop() {
  if (anim_count == 0) {
    // no animations at all - kaomojis keep Geedo alive while we retry.
    // "confused" rather than "sad": this is a lost-the-Hub face, and he is
    // never meant to look miserable at his owner.
    // The eyes need neither WiFi nor downloads, so he stays alive and
    // looking around even with nothing fetched.
    idleEyes(8000);
    showRandomKaomojiFrom("confused", 1800);
    showStatus("No animations", "retrying...", "hold button 5s");
    idleDelay(1500);
    loadManifestAndAnims();
    return;
  }

  for (uint8_t i = 0; i < anim_count; i++) {
    if (isSystemAnim(anims[i])) continue;
    idleEyes(IDLE_EYES_MS);         // his resting face: wandering and blinking
    decayMood();
    if ((esp_random() % 100) < KAOMOJI_CHANCE_PCT)
      showMoodKaomoji(KAOMOJI_TIME_MS);
    playAnim(anims[i], PLAY_TIME_MS);   // then he goes and does something
  }
  saveMood();

  if (POLL_INTERVAL_MS > 0 && (millis() - lastPoll) > POLL_INTERVAL_MS) {
    Serial.println("Polling...");

    if (loadManifestAndAnims()) {
      Serial.printf("Now %d animations\n", anim_count);
    }
    checkFirmwareUpdate();
    lastPoll = millis();
  }
}
