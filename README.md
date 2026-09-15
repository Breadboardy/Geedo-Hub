# Geedo Hub

This is what every Geedo talks to. It serves animations and firmware updates
over the air, and it is where people share what they drew for him.

- **The Hub** — https://breadboardy.github.io/Geedo-Hub/
- **Draw one** — https://breadboardy.github.io/Geedo-Hub/make.html
- **Studio** — https://breadboardy.github.io/Geedo-Hub/studio/
- **Redeem a code** — https://breadboardy.github.io/Geedo-Hub/unlock.html

## How an animation gets on here

1. Draw it in the Studio and press **Publish**. That saves a `.geedo.json`
   and opens the [submission form](https://github.com/Breadboardy/Geedo-Hub/issues/new?template=publish-animation.yml).
2. The bot checks the file the way the robot would (size, speed, the flash
   rule) and posts a preview on the issue. Nothing is published yet.
3. A person looks at it. Every Geedo downloads everything on this list and
   most of the people watching those screens are kids, so nothing goes out
   unseen. A yes is the `approved` label; the bot packs it, lists it with the
   maker's name and the date, signs the manifest and pushes.
4. Every Geedo picks it up at its next check, within the minute.

The hardware design and firmware source are not public.
