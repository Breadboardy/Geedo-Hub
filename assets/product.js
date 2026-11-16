/* The shop, in one place.

   Geedo is not on sale yet and has no price. When either is known, fill it
   in here and every page follows by itself:

     price    what he costs, written the way it should read ("£39", "$49").
              Empty, and the pages say "Price to be announced".
     buyUrl   the page where somebody pays for him (the shop, a campaign).
              Empty, and every buy button says "Get notified" and goes to
              notifyUrl instead.
     notifyUrl where people wait to hear: the Discord for now; a campaign's
              "notify me on launch" page works here too.

   Nothing else needs touching. A page marks what should follow with
   attributes, and the pages read right with this file missing: the words in
   the HTML are the not-on-sale-yet ones.

     data-geedo-price          its text becomes the price
     data-geedo-buy            a link: where it goes and what it says
       data-soon="..."           the words while he is not on sale
       data-sale="..."           the words once he is
     data-geedo-soon           shown only while he is not on sale
     data-geedo-sale           shown only once he is                       */
window.GeedoProduct = {
  price: '',
  buyUrl: '',
  notifyUrl: 'https://discord.gg/Tp6urXEMQd',
};

(function () {
  const P = window.GeedoProduct, onSale = !!P.buyUrl;
  function apply() {
    document.documentElement.classList.toggle('on-sale', onSale);
    for (const el of document.querySelectorAll('[data-geedo-price]'))
      el.textContent = P.price || 'Price to be announced';
    for (const a of document.querySelectorAll('[data-geedo-buy]')) {
      a.href = onSale ? P.buyUrl : P.notifyUrl;
      a.textContent = onSale ? (a.dataset.sale || 'Buy Geedo') : (a.dataset.soon || 'Get notified');
      a.target = '_blank'; a.rel = 'noopener';
    }
    for (const el of document.querySelectorAll('[data-geedo-soon]')) el.hidden = onSale;
    for (const el of document.querySelectorAll('[data-geedo-sale]')) el.hidden = !onSale;
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', apply); else apply();
})();
