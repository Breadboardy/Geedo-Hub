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
Hi! Let's set me up:
1. phone WiFi list
2. join this one:
   [ GEEDO-Setup ]
no password needed!
```

On your phone, open WiFi settings and connect to **GEEDO-Setup**. A page opens
by itself. Pick your home WiFi from the list, type your password, hit save.

**3. That's it.** Geedo remembers your WiFi forever. He quietly connects,
grabs his animations (`getting my stuff...`), and comes alive. From then on
every startup is just: boot animation, straight to his eyes — the setup
screen only ever comes back if he can't reach your WiFi.

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

**Secret:** pet him ten times in a row and he sings his theme song.

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
| `Hi! Let's set me up` | He has no WiFi saved — join **GEEDO-Setup** on your phone. Also appears if his saved WiFi stops working |
| update animation looping | Installing an update — leave him powered until he reboots by himself |
| big face + `updated! rebooting` | Update finished, restarting |
| big face + `getting my stuff...` | Downloading his animations |
| `Fetch FAILED` / `check HUB` | He reached WiFi but not the Hub — see troubleshooting |
| `No WiFi` / `and no cache` | Can't connect and has nothing saved to play |
| `No animations` / `retrying...` | Connected, but the animation list came back empty |
| `KEEP HOLDING` | You're holding the button — keep going to erase WiFi, or let go |
| `WIFI ERASED` | WiFi wiped, restarting into setup |

---

## Sleeping

Leave Geedo alone for about 20 minutes and he nods off: the screen dims and
he curls up. **Tap the button and he wakes up** — he'll open his eyes and
stretch. While he's asleep he stirs every so often, has a look around for
half a minute, and settles back down, the way a cat does.

He still checks for new animations and updates while asleep, so nothing is
missed.

## Sounds

Geedo chirps softly. Waking up, being petted (the more you pet him the
higher and happier the chirp), nodding off, and finishing an update all have
their own little sound. If something goes wrong he makes two quiet low notes
— an "oops", never an alarm.

He's deliberately quiet. He's a desk companion, not a smoke alarm.

*Robots built before board revision 4.4 have no buzzer and stay silent —
everything else works exactly the same.*

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

## The Geedo Discord

Other owners hang out here:

**https://discord.gg/Tp6urXEMQd**

It's where new animation packs get announced, where you can show off what
you've drawn in the Studio, and where giveaways happen — pick up the
**Giveaways** role when you join and you'll get pinged when one starts.

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

**The screen says `Update failed` with a code**
He tried to install an update and something went wrong — he keeps retrying by
himself, so usually you can just wait. If it keeps happening, the code tells
support exactly where it broke:

| Code | Meaning |
|---|---|
| `D404` | The update file isn't on the server (bad publish) |
| `D-1` / other negative | Couldn't reach the server — WiFi or internet hiccup |
| `S...` | The server sent an empty file |
| `F...` | No room to stage the update |
| `W...` | Connection dropped mid-download (number = bytes he got) |
| `C...` | The downloaded file failed verification |

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
