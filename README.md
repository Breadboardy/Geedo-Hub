# Geedo Hub

This is what every Geedo talks to. It serves animations and firmware updates
over the air, and it is where people share what they drew for him.

- **The Hub** — https://breadboardy.github.io/Geedo-Hub/
- **Buy Geedo** — https://breadboardy.github.io/Geedo-Hub/buy.html
- **Draw one** — https://breadboardy.github.io/Geedo-Hub/make.html
- **Studio** — https://breadboardy.github.io/Geedo-Hub/studio/
- **Redeem a code** — https://breadboardy.github.io/Geedo-Hub/unlock.html

## The shop

Everything that sells him and is not settled yet - the price, where he is
bought, the email box, real photos and a video, what is in his box, where
he ships, what people who have one say - is in one file,
[`assets/product.js`](assets/product.js). While a line there is empty, its
part of the page is a striped box labelled "Placeholder" that says what goes
there; fill the line in and the real thing takes its place. A placeholder
never pretends: the price reads "Price to be announced", there is no
invented review, and the email box cannot be typed in until it has somewhere
to send to. Set `placeholders: false` in that file and an empty part is left
off the page instead. To look ahead at the page once he can be bought, put
`?preview=sale` on the end of the address:
[Buy, once he is on sale](https://breadboardy.github.io/Geedo-Hub/buy.html?preview=sale).
Real photos and the video go in `assets/real/`.

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

### Publishing with a Geedo account

The Studio can also send a drawing straight in, for a maker signed in with a
Geedo account (a maker name and a password; no email). That needs a small
server, because these pages are files and cannot take anything in. Its
address goes in [`assets/hub.json`](assets/hub.json). **While that is empty
there are no accounts, and step 1 above is how it works.**

With an address there, step 1 becomes "press Publish", and the rest is the
same: the "Community inbox" workflow collects what is waiting on the server
(every quarter of an hour, once its timer is switched on in the workflow
file; or when it is run by hand), checks it and files the same review issue; a
person adds `approved`; and the maker sees what became of it in the Studio,
under My animations. The server cannot publish anything and has no access to
this repository. The workflow reaches it with the `GEEDO_HUB_KEY` secret.

The Studio's **Community** button shows everything on the Hub inside the
editor, to watch and to open for a remix. It reads the lists on this site
and needs no server.

The hardware design and firmware source are not public.
