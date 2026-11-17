/* The shop, in one place.

   Everything that sells Geedo and is not known yet lives here: the price,
   the way to pay, the email box, real photos and a video of him, what is in
   his box, where he ships, what happens if one breaks, and what people who
   have one say. Fill a line in and every page follows by itself.

   WHILE A LINE IS EMPTY, ITS PART OF THE PAGE IS A PLACEHOLDER: a striped
   box with a "Placeholder" label that says what goes there. It is on the
   live pages for everybody, and it is replaced by the real thing the moment
   its line is filled in. A placeholder never pretends: there is no made-up
   price (the pages say "Price to be announced"), no invented review, and
   the email box cannot be typed in until it has somewhere to send to.
   Set placeholders to false below and an empty part is simply not there.

   To look ahead, open a page with ?preview on the end:

     buy.html?preview          the email box as it will work beside the buttons
     buy.html?preview=sale     ...and the page once he can be bought, with a
                               stand-in price and buy button

   The pages read right with this file missing: the words in the HTML are
   the not-on-sale-yet ones, and every part below starts hidden.

   A page marks what should follow with attributes:

     data-geedo-price            its text becomes the price
     data-geedo-buy              a link: where it goes and what it says
       data-soon / data-sale       its words before and after he is on sale
       data-with-email             its words when an email box sits beside it
     data-geedo-soon / -sale     shown only before / only once he is on sale
     data-geedo-noprice          shown only while there is no price
     data-geedo-email-on / -off  shown only when there is / is not an email box
     data-geedo-part="..."       a part that waits for the real thing: email,
                                 video, photos, box, shipping, promise, reviews
     data-geedo-section          a section that is there when a part in it is */
window.GeedoProduct = {

  // ---- placeholders -------------------------------------------------------
  placeholders: true,   // true: a part that is still empty below shows as a striped,
                        // labelled placeholder. false: it is left off the page.

  // ---- the price, and the way to pay --------------------------------------
  price: '',        // what he costs, written the way it should read: '$49', '£39'.
                    // Empty, and the pages say "Price to be announced".
  buyUrl: '',       // the page where somebody pays for him: a shop, a campaign.
                    // Empty, and every buy button says "Get notified" instead.
  buyWord: '',      // what the buy button says once buyUrl is set. Empty is
                    // "Buy Geedo"; "Pre-order Geedo" and "Back him on Kickstarter" fit too.
  notifyUrl: 'https://discord.gg/Tp6urXEMQd',   // where "Get notified" goes

  // ---- the email box ------------------------------------------------------
  // A box for an email address, beside every "Get notified". It needs a
  // newsletter or form service to send the address to (the account has to be
  // an adult's: their rules ask for 18+). The service gives you the address
  // its form posts to, and the name it wants the email field to have.
  email: {
    action: '',     // 'https://...' - empty, and the box is a placeholder nobody can type in
    field: 'email', // almost always 'email'; the service's own form says
    note: 'Only news about Geedo. Unsubscribe any time.',   // must be true of the service you pick
  },

  // ---- him, for real ------------------------------------------------------
  // Put the files in assets/real/. A video of about fifteen seconds, no
  // sound needed (it plays muted, on a loop): tap him, he perks up. And
  // three or four photos: in a hand for his size, on a desk, his face close.
  video: {
    src: '',        // 'assets/real/geedo.mp4'
    poster: '',     // 'assets/real/geedo.jpg': one still from it, shown while it loads
  },
  photos: [
    // { src: 'assets/real/hand.jpg', alt: 'Geedo sitting in the palm of a hand' },
  ],

  // ---- the answers that make it safe to buy -------------------------------
  inTheBox: [
    // 'Geedo', 'A USB-C cable', ...   exactly what is in the box, and nothing that is not
  ],
  shipping: '',     // where he ships to, and when: 'Ships to the US and Canada. The first batch posts in March.'
  promise: '',      // what happens if one arrives broken or stops working, in a sentence or two

  // ---- people who have one ------------------------------------------------
  // Real people's real words only, with their permission. Never written for them.
  reviews: [
    // { quote: 'What they said.', name: 'First name, or a handle', note: 'early tester' },
  ],
};

(function () {
  const P = window.GeedoProduct || {};
  const mode = new URLSearchParams(location.search).get('preview');     // null, '' or 'sale'
  const preview = mode !== null;                          // the owner looking ahead
  const standIns = preview || P.placeholders !== false;   // an empty part shows its placeholder

  // What stands in for each empty line. Every word of it says that it is a
  // placeholder: none of it could be taken for a fact.
  const STAND_IN = {
    price: '$00', buyUrl: '#the-page-where-he-is-bought',
    email: { action: '', field: 'email', note: 'A line about what the emails are, and that they can be stopped.' },
    video: { src: '', poster: '' },
    photos: [{ alt: 'Photo: Geedo in a hand, for his size' }, { alt: 'Photo: on a desk, beside a laptop' }, { alt: 'Photo: his face, close up' }],
    inTheBox: ['Geedo', 'What else is in the box', 'And the next thing'],
    shipping: 'Where he ships to, and when the first batch posts.',
    promise: 'What happens if one arrives broken, or stops working.',
    reviews: [{ quote: 'What a real owner said about him goes here.', name: 'Their first name', note: 'early tester' },
              { quote: 'A second one, in their own words.', name: 'Another name', note: 'early tester' },
              { quote: 'And a third. Only real ones, with permission.', name: 'A third name', note: 'early tester' }],
  };

  const has = {
    email: !!(P.email && P.email.action),
    video: !!(P.video && P.video.src),
    photos: Array.isArray(P.photos) && P.photos.some(p => p && p.src),
    box: Array.isArray(P.inTheBox) && P.inTheBox.length > 0,
    shipping: !!P.shipping, promise: !!P.promise,
    reviews: Array.isArray(P.reviews) && P.reviews.some(r => r && r.quote),
  };
  const onSale = !!P.buyUrl || mode === 'sale';
  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
  // a stand-in: a striped box that says what goes there
  const standIn = (cls, text) => { const n = el('div', 'stand-in ' + (cls || '')); n.append(el('span', 'stand-in-tag', 'Placeholder'), el('span', 'stand-in-what', text)); return n; };
  // shown if it is real, or else as its stand-in. Returns true when the stand-in is what is showing.
  function part(node, real) {
    node.hidden = !(real || standIns);
    const fake = !real && standIns;
    node.classList.toggle('is-stand-in', fake);
    return fake;
  }

  function price() {
    const text = P.price || (mode === 'sale' ? STAND_IN.price : '');
    for (const n of document.querySelectorAll('[data-geedo-price]')) {
      n.textContent = text || 'Price to be announced';
      n.classList.toggle('is-stand-in', !P.price && !!text);
    }
    for (const a of document.querySelectorAll('[data-geedo-buy]')) {
      a.href = P.buyUrl || (mode === 'sale' ? STAND_IN.buyUrl : P.notifyUrl || a.href);
      a.textContent = onSale ? (P.buyWord || a.dataset.sale || 'Buy Geedo') : (a.dataset.soon || 'Get notified');
      if (P.buyUrl || !onSale) { a.target = '_blank'; a.rel = 'noopener'; } else { a.removeAttribute('target'); }
      a.classList.toggle('is-stand-in', onSale && !P.buyUrl);
    }
    for (const n of document.querySelectorAll('[data-geedo-soon]')) n.hidden = onSale;
    for (const n of document.querySelectorAll('[data-geedo-sale]')) n.hidden = !onSale;
    // a price that is known reads as one, on sale yet or not - and "the price is not set" is no longer true
    document.documentElement.classList.toggle('has-price', !!text);
    for (const n of document.querySelectorAll('[data-geedo-noprice]')) n.hidden = !!text;
  }

  // The email box. A plain form, posted by the browser to the service in a
  // new tab (which is where the service says "check your inbox"), so it
  // works with any of them and needs nothing of this page but the address.
  //
  // With nowhere to send to it is a placeholder. On the live page that is a
  // box nobody can type in - an address must never be taken and dropped -
  // and the Discord button beside it stays the way to hear. In a preview it
  // can be tried, and says that nothing was sent.
  function email() {
    const cfg = has.email ? P.email : STAND_IN.email;
    let n = 0, live = false;
    for (const form of document.querySelectorAll('form[data-geedo-part="email"]')) {
      // once he can be bought, the button is the thing: the box is for the wait before
      const shown = !onSale && (has.email || standIns), fake = shown && !has.email;
      form.hidden = !shown;
      form.classList.toggle('is-stand-in', fake);
      if (!shown) continue;
      const input = form.querySelector('input[type="email"]'), note = form.querySelector('.signup-note');
      const send = form.querySelector('button');
      const id = 'geedo-email-' + (++n);
      input.id = id; input.name = cfg.field || 'email';
      const label = form.querySelector('label'); if (label) label.htmlFor = id;
      const dead = fake && !preview;      // a placeholder on the live page
      input.disabled = dead; if (send) send.disabled = dead;
      if (note) note.textContent = dead ? 'The email box goes here. It is not switched on yet.' : cfg.note || '';
      if (dead) continue;
      live = true;
      if (!fake) { form.action = cfg.action; form.method = 'post'; form.target = '_blank'; }
      form.addEventListener('submit', e => {
        if (fake) e.preventDefault();
        // after the browser has taken the address: the box becomes its thanks
        setTimeout(() => {
          form.classList.add('sent');
          const said = form.querySelector('.signup-thanks');
          if (said) said.textContent = fake ? 'Preview: nothing was sent. The address your form service gives you goes in assets/product.js.'
                                            : 'Thank you. Look for an email to confirm it.';
          input.value = '';
        }, 60);
      });
      // with a box to type in, the box is the way to hear: the Discord button
      // beside it says what it is and steps back, and "the Discord hears
      // first" is no longer the news
      for (const a of form.parentElement.querySelectorAll('[data-geedo-buy][data-with-email]')) {
        a.textContent = a.dataset.withEmail; a.classList.remove('primary');
      }
      for (const s of form.parentElement.querySelectorAll('[data-geedo-soon].soon')) s.hidden = true;
    }
    // words elsewhere on the page that say how to hear: the box when there is one that works, the Discord when there is not
    for (const n of document.querySelectorAll('[data-geedo-email-on]')) n.hidden = !live;
    for (const n of document.querySelectorAll('[data-geedo-email-off]')) n.hidden = live;
  }

  function real() {
    const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
    for (const box of document.querySelectorAll('[data-geedo-part="video"]')) {
      const fake = part(box, has.video);
      if (box.hidden) continue;
      if (fake) { box.replaceChildren(standIn('wide', 'Video: about fifteen seconds of the real Geedo. Tap him, he perks up.')); continue; }
      const v = el('video');
      v.src = P.video.src; if (P.video.poster) v.poster = P.video.poster;
      v.muted = true; v.loop = true; v.playsInline = true; v.preload = 'metadata';
      v.setAttribute('muted', ''); v.setAttribute('playsinline', '');
      v.setAttribute('aria-label', 'Geedo on a desk, filmed');
      if (calm) v.controls = true; else v.autoplay = true;
      box.replaceChildren(v);
    }
    for (const grid of document.querySelectorAll('[data-geedo-part="photos"]')) {
      const fake = part(grid, has.photos);
      if (grid.hidden) continue;
      const list = fake ? STAND_IN.photos : P.photos.filter(p => p && p.src);
      grid.replaceChildren(...list.map(p => {
        if (fake) return standIn('tall', p.alt);
        const fig = el('figure', 'real-photo'), img = el('img');
        img.src = p.src; img.alt = p.alt || 'Geedo'; img.loading = 'lazy'; img.decoding = 'async';
        fig.append(img); return fig;
      }));
      grid.style.setProperty('--n', Math.min(4, list.length));
    }
  }

  function answers() {
    for (const ul of document.querySelectorAll('[data-geedo-part="box"]')) {
      const tile = ul.closest('.answer') || ul, fake = part(tile, has.box);
      if (tile.hidden) continue;
      ul.replaceChildren(...(fake ? STAND_IN.inTheBox : P.inTheBox).map(t => el('li', '', t)));
    }
    for (const [key, text] of [['shipping', P.shipping], ['promise', P.promise]]) {
      for (const p of document.querySelectorAll('[data-geedo-part="' + key + '"]')) {
        const tile = p.closest('.answer') || p, fake = part(tile, has[key]);
        if (!tile.hidden) p.textContent = fake ? STAND_IN[key] : text;
      }
    }
    // the row is there if any of its tiles is
    for (const row of document.querySelectorAll('.answers')) row.hidden = ![...row.children].some(c => !c.hidden);
  }

  function reviews() {
    for (const grid of document.querySelectorAll('[data-geedo-part="reviews"]')) {
      const fake = part(grid, has.reviews);
      const section = grid.closest('[data-geedo-section]');
      if (section) section.hidden = grid.hidden;
      if (grid.hidden) continue;
      grid.replaceChildren(...(fake ? STAND_IN.reviews : P.reviews.filter(r => r && r.quote)).map(r => {
        const fig = el('figure', 'quote' + (fake ? ' is-stand-in' : '')), who = el('figcaption');
        fig.append(el('blockquote', '', r.quote));
        who.append(el('b', '', r.name || ''), r.note ? el('span', '', r.note) : '');
        fig.append(who); return fig;
      }));
    }
  }

  // a section that holds only parts is there when one of them is
  function sections() {
    for (const s of document.querySelectorAll('[data-geedo-section]')) {
      const parts = [...s.querySelectorAll('[data-geedo-part]')];
      if (parts.length) s.hidden = parts.every(p => p.hidden || (p.closest('.answer') || p).hidden);
    }
  }

  function bar() {
    if (!preview || document.querySelector('.preview-bar')) return;
    document.documentElement.classList.add('preview');
    const b = el('div', 'preview-bar');
    b.append(el('b', '', 'Preview'), el('span', '', P.placeholders !== false
      ? ' - looking ahead. The striped parts are placeholders, until assets/product.js is filled in. '
      : ' - the striped parts are placeholders. Visitors do not see them until assets/product.js is filled in. '));
    const other = el('a', '', mode === 'sale' ? 'See it before he is on sale' : 'See it once he is on sale');
    other.href = location.pathname + (mode === 'sale' ? '?preview' : '?preview=sale');
    b.append(other);
    document.body.append(b);
  }

  function apply() {
    document.documentElement.classList.toggle('on-sale', onSale);
    price(); email(); real(); answers(); reviews(); sections(); bar();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', apply); else apply();
})();
