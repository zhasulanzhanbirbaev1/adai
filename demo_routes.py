"""
demo_routes.py — демо-режим для показа жюри.

ПРИНЦИП: ничего не трогаем. Только добавляем.
Ни один существующий эндпоинт, ни одна таблица, ни app.html не меняются.
Если демо упадёт — основной продукт этого не заметит.

ПОДКЛЮЧЕНИЕ — одна строка в webhook_server.py, рядом с другими роутерами:

    from demo_routes import demo_router
    app.include_router(demo_router)

Открывается по адресу:  https://ваш-домен/demo

ЧТО ДЕЛАЕТ:
  - три поля: ниша, оффер, город
  - генерирует баннеры тем же кодом, что и основной продукт
  - НЕ требует Facebook, НЕ пишет в БД, НЕ списывает генерации
  - кнопка «Запустить рекламу» показана неактивной — видно, что
    продукт целый, просто у гостя нет подключённого аккаунта
"""

from __future__ import annotations

import asyncio
import base64
import os
import time
from collections import defaultdict

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

demo_router = APIRouter(prefix="/demo", tags=["demo"])

# ─────────────────────────────────────────────────────────────────────
# ЛИМИТЫ — защита баланса OpenAI
# ─────────────────────────────────────────────────────────────────────
# При балансе 5,75 $ и цене около 0,22 $ за генерацию хватает примерно
# на 26 прогонов. После выступления ссылку могут разослать по чату
# программы, поэтому потолок обязателен.

MAX_PER_IP = int(os.getenv("DEMO_MAX_PER_IP", "1"))
MAX_TOTAL = int(os.getenv("DEMO_MAX_TOTAL", "20"))

_used_by_ip: dict = defaultdict(int)
_total_used = 0
_started = time.time()


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (
        request.client.host if request.client else "unknown")


# ─────────────────────────────────────────────────────────────────────
# ГЕНЕРАЦИЯ — вызывает тот же пайплайн, что и основной продукт.
# НЕ вызывает: can_generate, increment_generations, Facebook.
# ─────────────────────────────────────────────────────────────────────

async def _generate(niche: str, offer: str, city: str) -> list:
    """Возвращает список из 1-3 элементов:
       [{"image": "data:image/jpeg;base64,...", "headline": "...", "cta": "..."}, ...]
    """
    from image_generator import generate_3_creatives_concept, generate_image
    from banner_composer import compose_creative_banner

    brief = {
        "niche":           niche,
        "geo":             city or "Казахстан",
        "description":     offer,
        "offers":          offer,
        "audience":        "",
        "utp":             "",
        "whatsapp_number": "",
        "client_photo":    False,
    }

    concepts_data = await generate_3_creatives_concept(brief)
    variants = concepts_data.get("variants", [])[:3]

    if not variants:
        missing   = concepts_data.get("missing", [])
        questions = concepts_data.get("questions", [])
        detail = ("Заполните подробнее: " + "; ".join(questions or missing)
                  if (missing or questions) else "Укажите нишу и попробуйте снова")
        raise ValueError(detail)

    async def _one(v: dict) -> dict | None:
        import logging
        from fastapi.concurrency import run_in_threadpool
        try:
            img_bytes    = await generate_image(v["image_prompt_en"], size="1024x1536")
            banner_bytes = await run_in_threadpool(
                compose_creative_banner,
                img_bytes,
                v.get("text_overlay", {}),
                v.get("color_scheme", {}),
                v.get("font_style", "bold_sans"),
            )
            b64 = base64.b64encode(banner_bytes).decode()
            to  = v.get("text_overlay", {})
            return {
                "image":    f"data:image/jpeg;base64,{b64}",
                "headline": to.get("hook_headline", v.get("variant_name", "")),
                "cta":      to.get("cta_button", "Узнать подробнее"),
            }
        except Exception as exc:
            logging.getLogger(__name__).error("Demo banner error: %s", exc)
            return None

    results = await asyncio.gather(*[_one(v) for v in variants])
    banners  = [r for r in results if r is not None]

    if not banners:
        raise RuntimeError("Не удалось создать баннеры — попробуйте ещё раз")

    return banners


# ─────────────────────────────────────────────────────────────────────
# ЭНДПОИНТЫ
# ─────────────────────────────────────────────────────────────────────


@demo_router.post("/generate")
async def demo_generate(request: Request):
    global _total_used

    ip = _client_ip(request)

    if _total_used >= MAX_TOTAL:
        return JSONResponse(
            {"error": "Демо-лимит на сегодня исчерпан. "
                      "Напишите нам — покажем полную версию."},
            status_code=429)

    if _used_by_ip[ip] >= MAX_PER_IP:
        return JSONResponse(
            {"error": "Вы уже сгенерировали демо-баннеры. "
                      "Полная версия доступна после подключения аккаунта."},
            status_code=429)

    body  = await request.json()
    niche = (body.get("niche") or "").strip()[:80]
    offer = (body.get("offer") or "").strip()[:160]
    city  = (body.get("city") or "").strip()[:40]

    if not niche or not offer:
        return JSONResponse(
            {"error": "Заполните нишу и предложение"}, status_code=400)

    # считаем ДО генерации: иначе при параллельных запросах лимит протечёт
    _used_by_ip[ip] += 1
    _total_used += 1

    try:
        variants = await _generate(niche, offer, city)
        return {"ok": True, "variants": variants,
                "left": max(MAX_TOTAL - _total_used, 0)}
    except Exception as e:
        # откатываем счётчик: неудачная генерация не должна съедать лимит
        _used_by_ip[ip] -= 1
        _total_used -= 1
        return JSONResponse(
            {"error": "Не получилось сгенерировать. Попробуйте ещё раз.",
             "detail": type(e).__name__},
            status_code=500)


@demo_router.get("/stats")
async def demo_stats():
    """Открыть перед выступлением, чтобы видеть остаток."""
    return {"total_used": _total_used, "max_total": MAX_TOTAL,
            "left": max(MAX_TOTAL - _total_used, 0),
            "unique_ips": len(_used_by_ip),
            "uptime_min": round((time.time() - _started) / 60, 1)}


@demo_router.get("", response_class=HTMLResponse)
@demo_router.get("/", response_class=HTMLResponse)
async def demo_page():
    return HTMLResponse(DEMO_HTML)


# ─────────────────────────────────────────────────────────────────────
# СТРАНИЦА
# ─────────────────────────────────────────────────────────────────────

DEMO_HTML = r"""<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Adai — демо</title>
<style>
:root{--bg:#07070E;--surf:#12121F;--line:#24243A;--ink:#F3F3F8;
      --mute:#8C8CA6;--violet:#7C5CFF;--teal:#2DD4A0}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
body{background:var(--bg);color:var(--ink);
     font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
     padding:26px 20px 48px;max-width:560px;margin:0 auto;min-height:100vh}
.top{height:3px;background:linear-gradient(90deg,var(--violet),var(--teal));
     border-radius:2px;margin-bottom:26px}
h1{font-size:27px;font-weight:800;letter-spacing:-.02em;line-height:1.15}
.sub{color:var(--mute);font-size:15px;margin-top:9px;line-height:1.5}
label{display:block;font-size:12px;font-weight:600;letter-spacing:.08em;
      color:var(--mute);margin:20px 0 7px}
input{width:100%;background:var(--surf);border:1px solid var(--line);
      border-radius:11px;padding:14px 15px;color:var(--ink);font-size:16px;
      font-family:inherit;outline:none}
input:focus{border-color:var(--violet)}
button{width:100%;margin-top:26px;padding:16px;border:none;border-radius:11px;
       background:var(--violet);color:#fff;font-size:16px;font-weight:600;
       font-family:inherit;cursor:pointer}
button:disabled{opacity:.5;cursor:default}
.ghost{background:transparent;border:1px solid var(--line);color:var(--mute);
       margin-top:12px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.chip{background:var(--surf);border:1px solid var(--line);border-radius:100px;
      padding:7px 13px;font-size:13px;color:var(--mute);cursor:pointer}
.chip:active{border-color:var(--violet);color:var(--ink)}
#status{margin-top:22px;color:var(--mute);font-size:15px;line-height:1.5;
        display:none;text-align:center}
.dots::after{content:'';animation:d 1.4s infinite}
@keyframes d{0%{content:''}33%{content:'.'}66%{content:'..'}100%{content:'...'}}
#out{margin-top:28px;display:none}
.shot{width:100%;border-radius:13px;border:1px solid var(--line);
      margin-bottom:14px;display:block}
.cap{font-size:13px;color:var(--mute);margin:-6px 0 18px}
.note{background:rgba(124,92,255,.1);border:1px solid rgba(124,92,255,.3);
      border-radius:12px;padding:16px 17px;margin-top:22px;
      font-size:14px;line-height:1.55;color:#D6D6E4}
.err{background:rgba(255,107,107,.1);border-color:rgba(255,107,107,.35)}
</style></head><body>

<div class="top"></div>
<h1>Adai. Реклама без таргетолога</h1>
<p class="sub">Опишите бизнес в трёх полях. Через пару минут получите три
готовых рекламных баннера — так же, как их получает реальный клиент.</p>

<label>НИША</label>
<input id="niche" placeholder="Стоматология">
<div class="chips">
  <span class="chip" data-f="niche">Стоматология</span>
  <span class="chip" data-f="niche">Автосервис</span>
  <span class="chip" data-f="niche">Салон красоты</span>
  <span class="chip" data-f="niche">Кофейня</span>
</div>

<label>ПРЕДЛОЖЕНИЕ · обязательно с цифрой</label>
<input id="offer" placeholder="Виниры от 45 000 ₸, диагностика бесплатно">

<label>ГОРОД</label>
<input id="city" placeholder="Алматы" value="Алматы">

<button id="go">Сгенерировать баннеры</button>
<button class="ghost" disabled>Запустить рекламу · нужен аккаунт Facebook</button>

<div id="status"></div>
<div id="out"></div>

<div class="note" id="note" style="display:none">
  Дальше клиент нажимает «Запустить рекламу», и кампания уходит в Facebook
  и Instagram. Заявки приходят прямо в WhatsApp. В демо-режиме этот шаг
  отключён — для него нужен подключённый рекламный аккаунт.
</div>

<script>
document.querySelectorAll('.chip').forEach(c=>{
  c.onclick=()=>{document.getElementById(c.dataset.f).value=c.textContent}
});

const go=document.getElementById('go'),
      st=document.getElementById('status'),
      out=document.getElementById('out'),
      note=document.getElementById('note');

const steps=['Изучаю нишу и аудиторию','Придумываю три концепции',
             'Рисую баннеры','Собираю макеты'];

go.onclick=async()=>{
  const niche=document.getElementById('niche').value.trim();
  const offer=document.getElementById('offer').value.trim();
  const city=document.getElementById('city').value.trim();
  if(!niche||!offer){alert('Заполните нишу и предложение');return}

  go.disabled=true; out.style.display='none'; note.style.display='none';
  st.style.display='block'; st.className='';
  let i=0;
  st.innerHTML='<span class="dots">'+steps[0]+'</span>';
  const tick=setInterval(()=>{
    i=(i+1)%steps.length;
    st.innerHTML='<span class="dots">'+steps[i]+'</span>';
  },9000);

  try{
    const r=await fetch('/demo/generate',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({niche,offer,city})
    });
    const d=await r.json();
    clearInterval(tick);
    if(!r.ok){
      st.innerHTML='<div class="note err">'+(d.error||'Ошибка')+'</div>';
      return;
    }
    st.style.display='none';
    out.innerHTML=d.variants.map((v,n)=>{
      const src=(v.image||'').startsWith('http')?v.image:'data:image/png;base64,'+v.image;
      return '<img class="shot" src="'+src+'" alt="Вариант '+(n+1)+'">'+
             '<div class="cap">Вариант '+(n+1)+(v.headline?' · '+v.headline:'')+'</div>';
    }).join('');
    out.style.display='block';
    note.style.display='block';
  }catch(e){
    clearInterval(tick);
    st.innerHTML='<div class="note err">Не получилось. Попробуйте ещё раз.</div>';
  }finally{
    go.disabled=false;
  }
};
</script>
</body></html>"""
