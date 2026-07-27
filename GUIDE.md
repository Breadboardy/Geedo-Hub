# Geedo — Owner's Guide

Geedo is a little robot with a face. He connects to your WiFi, downloads
animations from the Geedo Hub, and pulls faces at you. New animations appear
on their own — you never have to plug him into a computer.

---

## First switch-on

**1. Turn him on.** Geedo plays his boot animation straight away, before he
even looks for WiFi.

**2. Join his setup network.** The screen shows:

```
FIRST-TIME SETUP

On your phone,
connect to WiFi:

> GEEDO-Setup
(no password)
```

On your phone, open WiFi settings and connect to **GEEDO-Setup**. A page opens
by itself. Pick your home WiFi from the list, type your password, hit save.

**3. That's it.** Geedo remembers your WiFi forever. He shows `WiFi OK` with his
IP address, checks for updates, downloads his animations, and starts playing.

The setup network stays open for 5 minutes. If it times out, switch Geedo off
and on again to reopen it.

---

## The button

The button on the outside of Geedo does two things:

| Do this | What happens |
|---|---|
| **Tap** | Pet him |
| **Hold 5 seconds** | Erase saved WiFi and start setup again |

**Petting.** Tap him and he reacts straight away — a happy face, and he
cheers up a little. Keep tapping and he gets more and more wound up until
he's positively giddy. He remembers: a Geedo who gets petted every day wears
a different set of faces than one who's been left alone on a shelf.

He drifts back to ordinary contentment if you ignore him for a few days, but
that's as far down as it goes. **Geedo never sulks at you** and never guilts
you into picking him up. He keeps his mood through a power cut and through
updates.

When you hold it, a countdown appears (`erasing WiFi in 3`). **Let go and
nothing happens** — it only wipes the WiFi if you hold the whole way through.
Use this if you change your WiFi password, move house, or give Geedo away.

There are two more buttons inside the case: **RESET** (restarts him, same as
switching off and on) and **BOOT** (only needed for factory recovery). You
should never need either.

---

## What Geedo's screens mean

| Screen | Meaning |
|---|---|
| `FIRST-TIME SETUP` | He has no WiFi saved yet — join **GEEDO-Setup** on your phone |
| `Connecting WiFi` / `<your network>` | Joining your network |
| `WiFi OK` / `<numbers>` | Connected. The numbers are his address on your network |
| `Checking` / `firmware...` | Asking the Hub whether there's a new version |
| `UPDATING v13` / `DO NOT UNPLUG` | Installing an update — leave him alone for a minute |
| `UPDATE OK` / `rebooting...` | Update finished, restarting |
| `Fetching` / `manifest...` | Downloading the animation list |
| `Fetch FAILED` / `check HUB` | He reached WiFi but not the Hub — see troubleshooting |
| `No WiFi` / `and no cache` | Can't connect and has nothing saved to play |
| `No animations` / `retrying...` | Connected, but the animation list came back empty |
| `KEEP HOLDING` | You're holding the button — keep going to erase WiFi, or let go |
| `WIFI ERASED` | WiFi wiped, restarting into setup |

---

## What he does when nothing's happening

Most of the time Geedo just sits there being alive: his eyes wander around,
he holds a look for a moment, glances somewhere else, and blinks now and then
on his own. He never repeats the same pattern twice.

Every so often he'll go and *do* something — one of his animations — and then
go back to looking around. Pet him and his eyes perk up straight away.

His eyes work with no WiFi and nothing downloaded, so he's never a blank
screen.

## Getting new animations

New animations land on Geedo **by themselves**. He checks the Hub every
60 seconds, downloads anything new, and saves it to his internal storage so it
survives a power cut.

Browse what's available at the **Geedo Hub**, or make your own in the Studio
and publish it — every Geedo picks it up within the minute.

Animations he has already downloaded keep playing even with the WiFi off, so
he still works in the car, on a trip, or when the internet is down.

---

## Charging

Plug in USB-C. The charge light on the board glows while charging and goes out
when full. Geedo runs happily while plugged in.

When you plug him in he plays his charging animation, and when the battery
runs low he'll warn you with a low-battery animation and a `LOW BATTERY`
screen (at most once every minute and a half — he won't spam you). If he
does run completely flat he just switches off; plug him in and he wakes.

---

## If something goes wrong

**Geedo is stuck on `FIRST-TIME SETUP` and GEEDO-Setup doesn't appear**
Some phones hide networks with no internet. Turn WiFi off and on, or look in
the full network list. Note that Geedo's setup network only runs 5 minutes
after switching on — restart him to reopen it.

**The setup page doesn't pop up after joining GEEDO-Setup**
Open a browser and go to `192.168.4.1` manually.

**`Fetch FAILED` / `check HUB`**
He's on your WiFi but can't reach the Hub. Usually the internet is down, or
you're on a network with a login page (school, café, hotel) — those block him.
He needs a normal home network. He'll keep retrying on his own.

**He connected before but not any more (you changed your WiFi password)**
Hold the button for 5 seconds. He'll erase the old WiFi and reopen setup.

**Screen is blank / frozen**
Press RESET inside the case, or switch him off and on. If the screen stays
blank but he still appears on your WiFi, the display ribbon is probably loose.

**He stopped playing some animations after a Hub update**
He has limited memory and loads as many animations as fit. If the library has
grown past what he can hold, later ones are skipped. This is a known limit —
see below.

**Nothing above helped**
Hold the button 5 seconds to reset WiFi and set him up fresh. That clears most
problems without losing his downloaded animations.

---

## Known limits on this revision

Being upfront about what this version can't do:

- **Limited animation memory.** Animations are held in RAM while playing.
  The library is close to the ceiling; past that, new animations are silently
  skipped rather than replacing old ones.
- **Captive-portal networks don't work.** Anything with a web login page
  (hotels, schools, cafés) will connect but never reach the Hub.
- **Updates are unsigned.** Firmware is fetched over HTTPS but not
  cryptographically signed, so Geedo trusts whatever the Hub serves.
