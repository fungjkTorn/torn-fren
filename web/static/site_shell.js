(()=>{"use strict";
const shell=document.querySelector(".tf-shell");if(!shell)return;
const path=location.pathname.replace(/\/$/,"")||"/";
let section=path==="/travel-decisions"?"travel":path==="/experimental"?"overview":"detail";
for(const a of shell.querySelectorAll("[data-tf-section]")){
  if(a.dataset.tfSection===section)a.setAttribute("aria-current","page");else a.removeAttribute("aria-current");
}
const menu=shell.querySelector(".tf-menu");
if(menu)menu.addEventListener("click",()=>{const open=shell.classList.toggle("open");menu.setAttribute("aria-expanded",String(open));});
for(const a of shell.querySelectorAll(".tf-nav a"))a.addEventListener("click",()=>{shell.classList.remove("open");menu?.setAttribute("aria-expanded","false");});
})();