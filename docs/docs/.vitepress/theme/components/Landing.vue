<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { withBase } from 'vitepress'
import '../styles/landing.css'

const root = ref<HTMLElement | null>(null)

const INSTALL_CMD = 'git clone https://github.com/asukaneko/nekobot.git'

const MCP_CONFIG = `{
  "mcpServers": {
    "nekobot": {
      "command": "python",
      "args": ["bot.py", "--mcp-only"],
      "env": { "PYTHONPATH": "." }
    }
  }
}`

const SRC_CODE = `# 克隆并安装
git clone https://github.com/asukaneko/nekobot.git
cd nekobot
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 配置环境变量（至少填写 Web 密码）
cp .env.example .env
# WEB_PASSWORD=your_web_password
# API_KEY / BASE_URL / MODEL —— 或在 Web 界面配置

# 启动（自动检测 QQ 配置）
python bot.py                # QQ + Web
python bot.py --only-web     # 仅 Web，默认 :5000
python bot.py --cli          # 仅 CLI`

const DOCKER_CODE = `# 官方镜像 · ghcr.io · amd64 / arm64
mkdir -p nekobot/data && cd nekobot
cp .env.example .env   # 至少填 WEB_PASSWORD

docker run -d --name nekobot --restart unless-stopped \\
  -p 5000:5000 \\
  -v "$(pwd)/data:/app/data" \\
  -v "$(pwd)/.env:/app/.env:ro" \\
  --env-file .env \\
  ghcr.io/asukaneko/nekobot:latest

# 访问 http://<服务器IP>:5000`

const tab = ref<'src' | 'docker'>('src')

const TYPE_LINES = [
  { cmd: 'python bot.py --mcp', out: 'MCP Server ready · transport=stdio · 13 tools exposed' },
  { cmd: 'python bot.py --mcp-connect http://192.168.1.100:5001/mcp', out: 'connected · streamable-http · handshake ok' },
]

let cleanups: Array<() => void> = []

onMounted(() => {
  const el = root.value
  if (!el) return

  /* ---------- nav: scrolled state ---------- */
  const nav = el.querySelector<HTMLElement>('#site-nav')
  if (nav) {
    const scrolledClasses = ['backdrop-blur-xl', 'bg-[rgba(10,11,13,0.72)]', 'border-[var(--border-soft)]']
    const topClasses = ['bg-transparent', 'border-transparent']
    const onScroll = () => {
      const scrolled = window.scrollY > 24
      scrolledClasses.forEach((c) => nav.classList.toggle(c, scrolled))
      topClasses.forEach((c) => nav.classList.toggle(c, !scrolled))
    }
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    cleanups.push(() => window.removeEventListener('scroll', onScroll))
  }

  /* ---------- reveal on scroll ---------- */
  const revealEls = el.querySelectorAll('[data-reveal]')
  if ('IntersectionObserver' in window) {
    const ob = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('revealed')
            ob.unobserve(entry.target)
          }
        })
      },
      { threshold: 0.12, rootMargin: '0px 0px -40px 0px' }
    )
    revealEls.forEach((node) => ob.observe(node))
    cleanups.push(() => ob.disconnect())
  } else {
    revealEls.forEach((node) => node.classList.add('revealed'))
  }

  /* ---------- copy buttons ---------- */
  const fallbackCopy = (text: string) => {
    const ta = document.createElement('textarea')
    ta.value = text
    document.body.appendChild(ta)
    ta.select()
    try { document.execCommand('copy') } catch (e) { /* noop */ }
    document.body.removeChild(ta)
  }

  el.querySelectorAll<HTMLElement>('.copy-btn').forEach((btn) => {
    let timer: ReturnType<typeof setTimeout> | undefined
    btn.addEventListener('click', () => {
      const text = btn.getAttribute('data-copy') || ''
      const iconCopy = btn.querySelector('.cb-icon-copy')
      const iconCheck = btn.querySelector('.cb-icon-check')
      const markDone = () => {
        iconCopy?.classList.add('hidden')
        iconCheck?.classList.remove('hidden')
        clearTimeout(timer)
        timer = setTimeout(() => {
          iconCopy?.classList.remove('hidden')
          iconCheck?.classList.add('hidden')
        }, 1600)
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(markDone, () => {
          fallbackCopy(text)
          markDone()
        })
      } else {
        fallbackCopy(text)
        markDone()
      }
    })
  })

  /* ---------- mcp terminal typer ---------- */
  const mcpDone = el.querySelector<HTMLElement>('#mcp-done')
  const mcpTyped = el.querySelector<HTMLElement>('#mcp-typed')
  if (mcpDone && mcpTyped) {
    let lineIdx = 0
    let charIdx = 0
    let typeTimer: ReturnType<typeof setInterval> | undefined
    let waitTimer: ReturnType<typeof setTimeout> | undefined

    const tick = () => {
      const meta = TYPE_LINES[lineIdx % TYPE_LINES.length]
      charIdx++
      mcpTyped.textContent = meta.cmd.slice(0, charIdx)
      if (charIdx >= meta.cmd.length) {
        if (typeTimer) clearInterval(typeTimer)
        typeTimer = undefined
        waitTimer = setTimeout(() => {
          const doneBlock = document.createElement('div')
          doneBlock.className = 'mb-1'

          const cmdLine = document.createElement('div')
          cmdLine.className = 'text-[var(--text-2)]'
          const dollar = document.createElement('span')
          dollar.className = 'text-[var(--signal)]'
          dollar.textContent = '$'
          cmdLine.appendChild(dollar)
          cmdLine.appendChild(document.createTextNode(' ' + meta.cmd))

          const outLine = document.createElement('div')
          outLine.className = 'text-[var(--text-3)]'
          outLine.textContent = meta.out

          doneBlock.appendChild(cmdLine)
          doneBlock.appendChild(outLine)
          mcpDone.appendChild(doneBlock)
          while (mcpDone.children.length > 3) {
            mcpDone.removeChild(mcpDone.firstChild as Node)
          }

          mcpTyped.textContent = ''
          charIdx = 0
          lineIdx++
          typeTimer = setInterval(tick, 42)
        }, 1600)
      }
    }

    typeTimer = setInterval(tick, 42)
    cleanups.push(() => {
      if (typeTimer) clearInterval(typeTimer)
      if (waitTimer) clearTimeout(waitTimer)
    })
  }
})

onUnmounted(() => {
  cleanups.forEach((fn) => fn())
  cleanups = []
})
</script>

<template>
  <div id="landing-root" ref="root" class="min-h-screen bg-[var(--bg)] text-[var(--text-1)]">
    <header id="site-nav" class="fixed top-0 left-0 right-0 z-50 transition-all duration-200 bg-transparent border-b border-transparent">
      <div class="mx-auto max-w-7xl px-5 md:px-8 h-[61px] flex items-center justify-between">
        <a href="#top" class="flex items-center gap-2.5 group">
          <img :src="withBase('/neko.png')" alt="NekoBot" class="w-7 h-7 rounded-md" />
          <span class="font-mono2 font-semibold text-[15px] tracking-tight">
            Neko<span class="text-[var(--signal)]">Bot</span>
          </span>
          <span class="hidden sm:inline-block font-mono2 text-[10px] px-1.5 py-0.5 rounded border border-[var(--border)] text-[var(--text-3)]">
            MIT
          </span>
        </a>

        <nav class="hidden md:flex items-center gap-1">
          <a href="#features" class="px-3 py-1.5 text-[13px] text-[var(--text-2)] hover:text-white rounded-full transition-colors">能力</a>
          <a href="#runtime" class="px-3 py-1.5 text-[13px] text-[var(--text-2)] hover:text-white rounded-full transition-colors">角色运行时</a>
          <a href="#architecture" class="px-3 py-1.5 text-[13px] text-[var(--text-2)] hover:text-white rounded-full transition-colors">架构</a>
          <a href="#mcp" class="px-3 py-1.5 text-[13px] text-[var(--text-2)] hover:text-white rounded-full transition-colors">MCP</a>
          <a href="#quickstart" class="px-3 py-1.5 text-[13px] text-[var(--text-2)] hover:text-white rounded-full transition-colors">快速开始</a>
        </nav>

        <div class="flex items-center gap-2">
          <a
            :href="withBase('/guide/quick-start')"
            class="flex items-center gap-1.5 rounded-full border border-[rgba(249,127,181,0.45)] bg-[rgba(249,127,181,0.08)] px-3.5 py-1.5 text-[13px] font-medium text-[var(--signal-soft)] transition-colors hover:bg-[rgba(249,127,181,0.16)] hover:text-white"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-book-open" aria-hidden="true"><path d="M12 7v14"></path><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"></path></svg>
            文档
          </a>

          <a
            href="https://github.com/asukaneko/nekobot"
            target="_blank"
            rel="noreferrer"
            class="flex items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--panel)] px-3.5 py-1.5 text-[13px] text-[var(--text-2)] transition-colors hover:border-[rgba(249,127,181,0.45)] hover:text-white"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-github" aria-hidden="true"><path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4"></path><path d="M9 18c-4.51 2-5-2-7-2"></path></svg>
            <span class="hidden sm:inline">GitHub</span>
            <span class="flex items-center gap-1 font-mono2 text-[11px] text-[var(--signal-soft)]">
              <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-star" aria-hidden="true"><path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z"></path></svg> Star
            </span>
          </a>
        </div>
      </div>
    </header>

    <main>
      <!-- ============ Hero ============ -->
      <section id="top" class="relative overflow-hidden pt-[61px]">
        <div class="hero-grid absolute inset-0 pointer-events-none"></div>
        <div class="glow-orb absolute -top-32 left-1/2 -translate-x-1/2 w-[720px] h-[420px] pointer-events-none"></div>
        <div class="glow-orb absolute top-40 -right-40 w-[420px] h-[420px] pointer-events-none opacity-60"></div>

        <div class="relative mx-auto max-w-7xl px-5 md:px-8 pt-16 md:pt-24 pb-20 md:pb-28">
          <div class="grid lg:grid-cols-[1.05fr_1fr] gap-14 lg:gap-10 items-center">
            <!-- left: text stack -->
            <div>
              <div data-reveal style="--i:0">
                <div class="flex flex-wrap items-center gap-2 mb-7">
                  <span class="font-mono2 text-[11px] px-2.5 py-1 rounded-full border border-[rgba(249,127,181,0.35)] text-[var(--signal-soft)] bg-[rgba(249,127,181,0.06)]">
                    开源 · MIT License
                  </span>
                  <span class="font-mono2 text-[11px] px-2.5 py-1 rounded-full border border-[var(--border)] text-[var(--text-3)]">
                    Python 3.10+
                  </span>
                  <span class="font-mono2 text-[11px] px-2.5 py-1 rounded-full border border-[var(--border)] text-[var(--text-3)]">
                    Docker Ready
                  </span>
                </div>
              </div>

              <div data-reveal style="--i:1">
                <h1 class="text-[42px] leading-[1.08] md:text-[64px] md:leading-[1.04] font-extrabold tracking-[-0.02em]">
                  不只是聊天接口，<br />
                  是<span class="text-gradient-signal">角色型智能体</span><br />
                  基础设施
                </h1>
              </div>

              <div data-reveal style="--i:2">
                <p class="mt-6 max-w-[52ch] text-[15px] md:text-[17px] leading-[1.8] text-[var(--text-2)]">
                  NekoBot 采用「统一 AI 内核 + 频道适配层」架构，内置角色运行时、记忆系统、
                  工具调用、工作区与可视化 Web 管理后台——一套可持续运行、可配置、
                  可观测、可扩展的多频道 AI 角色扮演系统。
                </p>
              </div>

              <div data-reveal style="--i:3">
                <div class="mt-9 flex flex-wrap items-center gap-3">
                  <a :href="withBase('/guide/quick-start')" class="cta-breathe group inline-flex items-center gap-2 rounded-lg bg-[var(--signal-strong)] px-5 py-2.5 text-[14px] font-semibold text-[#1a0b12] transition-transform hover:scale-[1.02] active:scale-[0.98]">
                    快速开始
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-arrow-right transition-transform group-hover:translate-x-0.5" aria-hidden="true"><path d="M5 12h14"></path><path d="m12 5 7 7-7 7"></path></svg>
                  </a>
                  <a href="https://github.com/asukaneko/nekobot" target="_blank" rel="noreferrer" class="inline-flex items-center gap-2 rounded-lg border border-[var(--border)] px-5 py-2.5 text-[14px] font-medium text-[var(--text-2)] transition-colors hover:border-[rgba(249,127,181,0.45)] hover:text-white">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-github" aria-hidden="true"><path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4"></path><path d="M9 18c-4.51 2-5-2-7-2"></path></svg>
                    查看源码
                  </a>
                </div>
              </div>

              <div data-reveal style="--i:4">
                <div class="mt-8 flex items-center gap-2 max-w-md rounded-lg code-block px-3.5 py-2.5">
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-terminal text-[var(--signal)] shrink-0" aria-hidden="true"><path d="M12 19h8"></path><path d="m4 17 6-6-6-6"></path></svg>
                  <code class="font-mono2 text-[12.5px] text-[var(--text-2)] truncate">
                    <span class="text-[var(--signal-soft)]">$</span> {{ INSTALL_CMD }}
                  </code>
                  <button
                    type="button"
                    class="copy-btn inline-flex items-center justify-center rounded-md border border-[var(--border)] bg-[var(--panel-2)] p-1.5 text-[var(--text-3)] transition-colors hover:text-[var(--signal-soft)] hover:border-[rgba(249,127,181,0.4)] ml-auto shrink-0"
                    :data-copy="INSTALL_CMD"
                    aria-label="复制"
                  >
                    <span class="cb-icon-copy"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-copy" aria-hidden="true"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"></rect><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"></path></svg></span>
                    <span class="cb-icon-check hidden"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-check text-emerald-400" aria-hidden="true"><path d="M20 6 9 17l-5-5"></path></svg></span>
                  </button>
                </div>
              </div>
            </div>

            <!-- right: floating dashboard mockup -->
            <div data-reveal style="--i:2" class="relative">
              <div class="relative float-y">
                <div class="dial-pulse rounded-xl border border-[var(--border)] bg-[rgba(18,19,22,0.72)] backdrop-blur-md p-2 shadow-[0_24px_80px_rgba(0,0,0,0.55)]">
                  <div class="flex items-center gap-1.5 px-2 pb-2">
                    <span class="terminal-dots flex gap-1.5">
                      <span style="background: #f97066"></span>
                      <span style="background: #fdb022"></span>
                      <span style="background: #32d583"></span>
                    </span>
                    <span class="ml-2 font-mono2 text-[10.5px] text-[var(--text-3)]">
                      nekobot · web console — :5000
                    </span>
                  </div>
                  <img :src="withBase('/landing/dashboard.png')" alt="NekoBot Web 管理后台 — AI 配置中心" class="rounded-lg w-full border border-[var(--border-soft)]" />
                </div>
                <img :src="withBase('/neko.png')" alt="NekoBot 吉祥物" class="float-y-slow absolute -bottom-10 -left-8 w-24 md:w-28 drop-shadow-[0_12px_28px_rgba(249,127,181,0.35)] select-none pointer-events-none" />
                <div class="absolute -top-4 -right-3 rounded-lg border border-[var(--border)] bg-[var(--panel)] px-3 py-2 shadow-lg">
                  <div class="font-mono2 text-[10px] text-[var(--text-3)]">CHANNELS ONLINE</div>
                  <div class="font-mono2 text-[13px] font-semibold text-[var(--signal-soft)]">QQ · Web · CLI · TG · 飞书</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ============ Stats band ============ -->
      <section class="border-t border-[var(--border-soft)]">
        <div class="mx-auto max-w-7xl px-5 md:px-8 py-14">
          <div class="grid grid-cols-2 lg:grid-cols-4 gap-8">
            <div data-reveal style="--i:0">
              <div>
                <div class="font-mono2 text-[36px] md:text-[44px] font-bold leading-none text-gradient-signal">5+</div>
                <div class="mt-2 text-[14px] font-medium">频道接入</div>
                <div class="mt-1 font-mono2 text-[11px] text-[var(--text-3)]">QQ / Web / CLI / Telegram / 飞书</div>
              </div>
            </div>
            <div data-reveal style="--i:1">
              <div>
                <div class="font-mono2 text-[36px] md:text-[44px] font-bold leading-none text-gradient-signal">13</div>
                <div class="mt-2 text-[14px] font-medium">MCP Tools</div>
                <div class="mt-1 font-mono2 text-[11px] text-[var(--text-3)]">状态 · 链路 · 队列 · 节点</div>
              </div>
            </div>
            <div data-reveal style="--i:2">
              <div>
                <div class="font-mono2 text-[36px] md:text-[44px] font-bold leading-none text-gradient-signal">6</div>
                <div class="mt-2 text-[14px] font-medium">六维关系模型</div>
                <div class="mt-1 font-mono2 text-[11px] text-[var(--text-3)]">亲密 / 信任 / 依赖 / 好感…</div>
              </div>
            </div>
            <div data-reveal style="--i:3">
              <div>
                <div class="font-mono2 text-[36px] md:text-[44px] font-bold leading-none text-gradient-signal">MIT</div>
                <div class="mt-2 text-[14px] font-medium">开源协议</div>
                <div class="mt-1 font-mono2 text-[11px] text-[var(--text-3)]">自由使用 · 欢迎贡献</div>
              </div>
            </div>
          </div>
        </div>

        <div class="relative border-t border-[var(--border-soft)] py-5 overflow-hidden">
          <div class="marquee-x flex w-max gap-3 pr-3">
            <span class="font-mono2 text-[12px] px-4 py-1.5 rounded-full border border-[var(--border)] text-[var(--text-2)] whitespace-nowrap bg-[var(--panel)]">QQ (NapCatQQ)</span>
            <span class="font-mono2 text-[12px] px-4 py-1.5 rounded-full border border-[var(--border)] text-[var(--text-2)] whitespace-nowrap bg-[var(--panel)]">Web Console</span>
            <span class="font-mono2 text-[12px] px-4 py-1.5 rounded-full border border-[var(--border)] text-[var(--text-2)] whitespace-nowrap bg-[var(--panel)]">CLI 终端</span>
            <span class="font-mono2 text-[12px] px-4 py-1.5 rounded-full border border-[var(--border)] text-[var(--text-2)] whitespace-nowrap bg-[var(--panel)]">Telegram</span>
            <span class="font-mono2 text-[12px] px-4 py-1.5 rounded-full border border-[var(--border)] text-[var(--text-2)] whitespace-nowrap bg-[var(--panel)]">飞书 Feishu</span>
            <span class="font-mono2 text-[12px] px-4 py-1.5 rounded-full border border-[var(--border)] text-[var(--text-2)] whitespace-nowrap bg-[var(--panel)]">Android 客户端</span>
            <span class="font-mono2 text-[12px] px-4 py-1.5 rounded-full border border-[var(--border)] text-[var(--text-2)] whitespace-nowrap bg-[var(--panel)]">MCP (Claude Code)</span>
            <span class="font-mono2 text-[12px] px-4 py-1.5 rounded-full border border-[var(--border)] text-[var(--text-2)] whitespace-nowrap bg-[var(--panel)]">MCP (Cursor)</span>
            <span class="font-mono2 text-[12px] px-4 py-1.5 rounded-full border border-[var(--border)] text-[var(--text-2)] whitespace-nowrap bg-[var(--panel)]">ChatGPT Agent</span>
            <span class="font-mono2 text-[12px] px-4 py-1.5 rounded-full border border-[var(--border)] text-[var(--text-2)] whitespace-nowrap bg-[var(--panel)]">QQ (NapCatQQ)</span>
            <span class="font-mono2 text-[12px] px-4 py-1.5 rounded-full border border-[var(--border)] text-[var(--text-2)] whitespace-nowrap bg-[var(--panel)]">Web Console</span>
            <span class="font-mono2 text-[12px] px-4 py-1.5 rounded-full border border-[var(--border)] text-[var(--text-2)] whitespace-nowrap bg-[var(--panel)]">CLI 终端</span>
            <span class="font-mono2 text-[12px] px-4 py-1.5 rounded-full border border-[var(--border)] text-[var(--text-2)] whitespace-nowrap bg-[var(--panel)]">Telegram</span>
            <span class="font-mono2 text-[12px] px-4 py-1.5 rounded-full border border-[var(--border)] text-[var(--text-2)] whitespace-nowrap bg-[var(--panel)]">飞书 Feishu</span>
            <span class="font-mono2 text-[12px] px-4 py-1.5 rounded-full border border-[var(--border)] text-[var(--text-2)] whitespace-nowrap bg-[var(--panel)]">Android 客户端</span>
            <span class="font-mono2 text-[12px] px-4 py-1.5 rounded-full border border-[var(--border)] text-[var(--text-2)] whitespace-nowrap bg-[var(--panel)]">MCP (Claude Code)</span>
            <span class="font-mono2 text-[12px] px-4 py-1.5 rounded-full border border-[var(--border)] text-[var(--text-2)] whitespace-nowrap bg-[var(--panel)]">MCP (Cursor)</span>
            <span class="font-mono2 text-[12px] px-4 py-1.5 rounded-full border border-[var(--border)] text-[var(--text-2)] whitespace-nowrap bg-[var(--panel)]">ChatGPT Agent</span>
          </div>
          <div class="absolute inset-y-0 left-0 w-24 bg-gradient-to-r from-[var(--bg)] to-transparent pointer-events-none"></div>
          <div class="absolute inset-y-0 right-0 w-24 bg-gradient-to-l from-[var(--bg)] to-transparent pointer-events-none"></div>
        </div>
      </section>

      <!-- ============ Features ============ -->
      <section id="features" class="relative py-24 md:py-32 border-t border-[var(--border-soft)]">
        <div class="mx-auto max-w-7xl px-5 md:px-8">
          <div class="mb-12 md:mb-16">
            <div data-reveal style="--i:0">
              <div class="flex items-center gap-3 mb-5">
                <span class="font-mono2 text-[12px] font-semibold text-[var(--signal)]">01</span>
                <span class="h-px w-8 bg-[var(--border)]"></span>
                <span class="font-mono2 text-[11px] tracking-[0.18em] uppercase text-[var(--text-3)]">Core Capabilities</span>
              </div>
            </div>
            <div data-reveal style="--i:1">
              <h2 class="text-[30px] md:text-[44px] leading-[1.15] font-bold tracking-[-0.015em] max-w-[18ch]">一个内核，装下角色的全部</h2>
            </div>
            <div data-reveal style="--i:2">
              <p class="mt-4 max-w-[58ch] text-[15px] leading-[1.8] text-[var(--text-2)]">不是把消息转发给模型那么简单。NekoBot 把角色扮演所需的运行时、记忆、工具与运维能力收进同一条流水线。</p>
            </div>
          </div>

          <div class="grid md:grid-cols-3 gap-4">
            <div data-reveal style="--i:0" class="md:col-span-2">
              <div class="card-glow group h-full rounded-xl p-6 flex flex-col gap-4 transition-colors hover:bg-[var(--panel-2)]">
                <div class="flex items-start justify-between">
                  <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-messages-square text-[var(--signal)] transition-transform duration-300 group-hover:scale-110" aria-hidden="true"><path d="M16 10a2 2 0 0 1-2 2H6.828a2 2 0 0 0-1.414.586l-2.202 2.202A.71.71 0 0 1 2 14.286V4a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path><path d="M20 9a2 2 0 0 1 2 2v10.286a.71.71 0 0 1-1.212.502l-2.202-2.202A2 2 0 0 0 17.172 19H10a2 2 0 0 1-2-2v-1"></path></svg>
                  <span class="font-mono2 text-[10px] px-2 py-0.5 rounded-full border border-[var(--border)] text-[var(--text-3)]">5 个频道适配器</span>
                </div>
                <div>
                  <h3 class="text-[17px] font-semibold mb-2">多渠道接入</h3>
                  <p class="text-[13.5px] leading-[1.75] text-[var(--text-2)]">QQ、Web、CLI、Telegram、飞书共用统一的 ChatRequest / ChatResponse 处理链路，一次部署，处处在线。</p>
                </div>
              </div>
            </div>

            <div data-reveal style="--i:1">
              <div class="card-glow group h-full rounded-xl p-6 flex flex-col gap-4 transition-colors hover:bg-[var(--panel-2)]">
                <div class="flex items-start justify-between">
                  <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-heart-pulse text-[var(--signal)] transition-transform duration-300 group-hover:scale-110" aria-hidden="true"><path d="M2 9.5a5.5 5.5 0 0 1 9.591-3.676.56.56 0 0 0 .818 0A5.49 5.49 0 0 1 22 9.5c0 2.29-1.5 4-3 5.5l-5.492 5.313a2 2 0 0 1-3 .019L5 15c-1.5-1.5-3-3.2-3-5.5"></path><path d="M3.22 13H9.5l.5-1 2 4.5 2-7 1.5 3.5h5.27"></path></svg>
                  <span class="font-mono2 text-[10px] px-2 py-0.5 rounded-full border border-[var(--border)] text-[var(--text-3)]">Affective Runtime</span>
                </div>
                <div>
                  <h3 class="text-[17px] font-semibold mb-2">角色运行时</h3>
                  <p class="text-[13.5px] leading-[1.75] text-[var(--text-2)]">实时情感引擎、六维关系模型、动态 PromptStack，把角色设定转化为持续一致的对话行为。</p>
                </div>
              </div>
            </div>

            <div data-reveal style="--i:2">
              <div class="card-glow group h-full rounded-xl p-6 flex flex-col gap-4 transition-colors hover:bg-[var(--panel-2)]">
                <div class="flex items-start justify-between">
                  <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-monitor-cog text-[var(--signal)] transition-transform duration-300 group-hover:scale-110" aria-hidden="true"><path d="M12 17v4"></path><path d="m14.305 7.53.923-.382"></path><path d="m15.228 4.852-.923-.383"></path><path d="m16.852 3.228-.383-.924"></path><path d="m16.852 8.772-.383.923"></path><path d="m19.148 3.228.383-.924"></path><path d="m19.53 9.696-.382-.924"></path><path d="m20.772 4.852.924-.383"></path><path d="m20.772 7.148.924.383"></path><path d="M22 13v2a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7"></path><path d="M8 21h8"></path><circle cx="18" cy="6" r="3"></circle></svg>
                  <span class="font-mono2 text-[10px] px-2 py-0.5 rounded-full border border-[var(--border)] text-[var(--text-3)]">Dashboard</span>
                </div>
                <div>
                  <h3 class="text-[17px] font-semibold mb-2">Web 控制台</h3>
                  <p class="text-[13.5px] leading-[1.75] text-[var(--text-2)]">会话、角色卡、模型、工作流、知识库、记忆、日志与调试——日常运维全部可视化。</p>
                </div>
              </div>
            </div>

            <div data-reveal style="--i:0">
              <div class="card-glow group h-full rounded-xl p-6 flex flex-col gap-4 transition-colors hover:bg-[var(--panel-2)]">
                <div class="flex items-start justify-between">
                  <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-folder-cog text-[var(--signal)] transition-transform duration-300 group-hover:scale-110" aria-hidden="true"><path d="M10.3 20H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.98a2 2 0 0 1 1.69.9l.66 1.2A2 2 0 0 0 12 6h8a2 2 0 0 1 2 2v3.3"></path><path d="m14.305 19.53.923-.382"></path><path d="m15.228 16.852-.923-.383"></path><path d="m16.852 15.228-.383-.923"></path><path d="m16.852 20.772-.383.924"></path><path d="m19.148 15.228.383-.923"></path><path d="m19.53 21.696-.382-.924"></path><path d="m20.772 16.852.924-.383"></path><path d="m20.772 19.148.924.383"></path><circle cx="18" cy="18" r="3"></circle></svg>
                  <span class="font-mono2 text-[10px] px-2 py-0.5 rounded-full border border-[var(--border)] text-[var(--text-3)]">Workspace</span>
                </div>
                <div>
                  <h3 class="text-[17px] font-semibold mb-2">工具与工作区</h3>
                  <p class="text-[13.5px] leading-[1.75] text-[var(--text-2)]">工具调用、文件读写、共享 / 私有工作区、文件变更预览与任务执行，对话中直接动手。</p>
                </div>
              </div>
            </div>

            <div data-reveal style="--i:1" class="md:col-span-2">
              <div class="card-glow group h-full rounded-xl p-6 flex flex-col gap-4 transition-colors hover:bg-[var(--panel-2)]">
                <div class="flex items-start justify-between">
                  <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-brain-circuit text-[var(--signal)] transition-transform duration-300 group-hover:scale-110" aria-hidden="true"><path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"></path><path d="M9 13a4.5 4.5 0 0 0 3-4"></path><path d="M6.003 5.125A3 3 0 0 0 6.401 6.5"></path><path d="M3.477 10.896a4 4 0 0 1 .585-.396"></path><path d="M6 18a4 4 0 0 1-1.967-.516"></path><path d="M12 13h4"></path><path d="M12 18h6a2 2 0 0 1 2 2v1"></path><path d="M12 8h8"></path><path d="M16 8V5a2 2 0 0 1 2-2"></path><circle cx="16" cy="13" r=".5"></circle><circle cx="18" cy="3" r=".5"></circle><circle cx="20" cy="21" r=".5"></circle><circle cx="20" cy="8" r=".5"></circle></svg>
                  <span class="font-mono2 text-[10px] px-2 py-0.5 rounded-full border border-[var(--border)] text-[var(--text-3)]">Cross-Provider</span>
                </div>
                <div>
                  <h3 class="text-[17px] font-semibold mb-2">模型适配</h3>
                  <p class="text-[13.5px] leading-[1.75] text-[var(--text-2)]">兼容 OpenAI Chat Completions / Responses、Anthropic、Gemini 接口，可接入 Deepseek、GLM、Kimi、MiMo 等。</p>
                </div>
              </div>
            </div>

            <div data-reveal style="--i:2">
              <div class="card-glow group h-full rounded-xl p-6 flex flex-col gap-4 transition-colors hover:bg-[var(--panel-2)]">
                <div class="flex items-start justify-between">
                  <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-blocks text-[var(--signal)] transition-transform duration-300 group-hover:scale-110" aria-hidden="true"><path d="M10 22V7a1 1 0 0 0-1-1H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5a1 1 0 0 0-1-1H2"></path><rect x="14" y="2" width="8" height="8" rx="1"></rect></svg>
                  <span class="font-mono2 text-[10px] px-2 py-0.5 rounded-full border border-[var(--border)] text-[var(--text-3)]">Extensible</span>
                </div>
                <div>
                  <h3 class="text-[17px] font-semibold mb-2">插件与技能</h3>
                  <p class="text-[13.5px] leading-[1.75] text-[var(--text-2)]">通过插件与技能系统扩展能力，而不破坏核心处理流程。</p>
                </div>
              </div>
            </div>

            <div data-reveal style="--i:0">
              <div class="card-glow group h-full rounded-xl p-6 flex flex-col gap-4 transition-colors hover:bg-[var(--panel-2)]">
                <div class="flex items-start justify-between">
                  <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-plug-zap text-[var(--signal)] transition-transform duration-300 group-hover:scale-110" aria-hidden="true"><path d="M6.3 20.3a2.4 2.4 0 0 0 3.4 0L12 18l-6-6-2.3 2.3a2.4 2.4 0 0 0 0 3.4Z"></path><path d="m2 22 3-3"></path><path d="M7.5 13.5 10 11"></path><path d="M10.5 16.5 13 14"></path><path d="m18 3-4 4h6l-4 4"></path></svg>
                  <span class="font-mono2 text-[10px] px-2 py-0.5 rounded-full border border-[var(--border)] text-[var(--text-3)]">MCP Server</span>
                </div>
                <div>
                  <h3 class="text-[17px] font-semibold mb-2">MCP 接口</h3>
                  <p class="text-[13.5px] leading-[1.75] text-[var(--text-2)]">以标准 MCP 协议暴露 Gateway 能力，Claude Code、Cursor、ChatGPT Agent 可直接调用。</p>
                </div>
              </div>
            </div>

            <div data-reveal style="--i:1">
              <div class="card-glow group h-full rounded-xl p-6 flex flex-col gap-4 transition-colors hover:bg-[var(--panel-2)]">
                <div class="flex items-start justify-between">
                  <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-audio-lines text-[var(--signal)] transition-transform duration-300 group-hover:scale-110" aria-hidden="true"><path d="M2 10v3"></path><path d="M6 6v11"></path><path d="M10 3v18"></path><path d="M14 8v7"></path><path d="M18 5v13"></path><path d="M22 10v3"></path></svg>
                  <span class="font-mono2 text-[10px] px-2 py-0.5 rounded-full border border-[var(--border)] text-[var(--text-3)]">TTS / STT</span>
                </div>
                <div>
                  <h3 class="text-[17px] font-semibold mb-2">语音能力</h3>
                  <p class="text-[13.5px] leading-[1.75] text-[var(--text-2)]">可插拔 TTS / STT 适配器：OpenAI 兼容、小米 MiMo、豆包，以及 faster-whisper 本地离线识别。</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ============ Runtime ============ -->
      <section id="runtime" class="relative py-24 md:py-32 border-t border-[var(--border-soft)] overflow-hidden">
        <div class="glow-orb absolute top-1/3 -left-48 w-[520px] h-[520px] pointer-events-none opacity-50"></div>
        <div class="relative mx-auto max-w-7xl px-5 md:px-8">
          <div class="mb-12 md:mb-16">
            <div data-reveal style="--i:0">
              <div class="flex items-center gap-3 mb-5">
                <span class="font-mono2 text-[12px] font-semibold text-[var(--signal)]">02</span>
                <span class="h-px w-8 bg-[var(--border)]"></span>
                <span class="font-mono2 text-[11px] tracking-[0.18em] uppercase text-[var(--text-3)]">Character Runtime</span>
              </div>
            </div>
            <div data-reveal style="--i:1">
              <h2 class="text-[30px] md:text-[44px] leading-[1.15] font-bold tracking-[-0.015em] max-w-[18ch]">角色不是一段 Prompt，是一套运行时</h2>
            </div>
            <div data-reveal style="--i:2">
              <p class="mt-4 max-w-[58ch] text-[15px] leading-[1.8] text-[var(--text-2)]">nbot/character/ 把「角色设定」转译为持续一致的对话行为：情绪有惯性，关系会生长，记忆被隔离。</p>
            </div>
          </div>

          <div class="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            <div data-reveal style="--i:0">
              <div class="card-glow group h-full rounded-xl p-6 transition-colors hover:bg-[var(--panel-2)]">
                <div class="flex items-baseline justify-between mb-8">
                  <span class="font-mono2 text-[34px] font-bold text-[rgba(249,127,181,0.85)] leading-none">P</span>
                  <span class="font-mono2 text-[10px] text-[var(--text-3)]">priority-aware</span>
                </div>
                <h3 class="font-mono2 text-[16px] font-semibold">PromptStack</h3>
                <div class="text-[12px] text-[var(--signal-soft)] mt-0.5 mb-3">动态提示词栈</div>
                <p class="text-[13.5px] leading-[1.75] text-[var(--text-2)]">按优先级动态拼装提示词，而不是把所有状态污染进历史消息，角色设定始终稳定可控。</p>
              </div>
            </div>

            <div data-reveal style="--i:1">
              <div class="card-glow group h-full rounded-xl p-6 transition-colors hover:bg-[var(--panel-2)]">
                <div class="flex items-baseline justify-between mb-8">
                  <span class="font-mono2 text-[34px] font-bold text-[rgba(249,127,181,0.85)] leading-none">S</span>
                  <span class="font-mono2 text-[10px] text-[var(--text-3)]">inertia-safe</span>
                </div>
                <h3 class="font-mono2 text-[16px] font-semibold">StateMachine</h3>
                <div class="text-[12px] text-[var(--signal-soft)] mt-0.5 mb-3">状态机</div>
                <p class="text-[13.5px] leading-[1.75] text-[var(--text-2)]">控制情绪惯性与关系平滑变化，避免单轮输入导致角色剧烈失真。</p>
              </div>
            </div>

            <div data-reveal style="--i:2">
              <div class="card-glow group h-full rounded-xl p-6 transition-colors hover:bg-[var(--panel-2)]">
                <div class="flex items-baseline justify-between mb-8">
                  <span class="font-mono2 text-[34px] font-bold text-[rgba(249,127,181,0.85)] leading-none">A</span>
                  <span class="font-mono2 text-[10px] text-[var(--text-3)]">self-tuning</span>
                </div>
                <h3 class="font-mono2 text-[16px] font-semibold">AutoState</h3>
                <div class="text-[12px] text-[var(--signal-soft)] mt-0.5 mb-3">自动状态评估</div>
                <p class="text-[13.5px] leading-[1.75] text-[var(--text-2)]">定期总结近期互动，自动调整情绪强度、精力与六维关系值。</p>
              </div>
            </div>

            <div data-reveal style="--i:0">
              <div class="card-glow group h-full rounded-xl p-6 transition-colors hover:bg-[var(--panel-2)]">
                <div class="flex items-baseline justify-between mb-8">
                  <span class="font-mono2 text-[34px] font-bold text-[rgba(249,127,181,0.85)] leading-none">M</span>
                  <span class="font-mono2 text-[10px] text-[var(--text-3)]">long / short term</span>
                </div>
                <h3 class="font-mono2 text-[16px] font-semibold">Memory</h3>
                <div class="text-[12px] text-[var(--signal-soft)] mt-0.5 mb-3">角色记忆</div>
                <p class="text-[13.5px] leading-[1.75] text-[var(--text-2)]">按角色、按用户隔离的长期与短期记忆，跨会话记得你是谁。</p>
              </div>
            </div>

            <div data-reveal style="--i:1">
              <div class="card-glow group h-full rounded-xl p-6 transition-colors hover:bg-[var(--panel-2)]">
                <div class="flex items-baseline justify-between mb-8">
                  <span class="font-mono2 text-[34px] font-bold text-[rgba(249,127,181,0.85)] leading-none">R</span>
                  <span class="font-mono2 text-[10px] text-[var(--text-3)]">per-turn plan</span>
                </div>
                <h3 class="font-mono2 text-[16px] font-semibold">ReactionPlan</h3>
                <div class="text-[12px] text-[var(--signal-soft)] mt-0.5 mb-3">反应策略</div>
                <p class="text-[13.5px] leading-[1.75] text-[var(--text-2)]">每轮回复前生成风格与行为策略，约束角色输出的语气与行动。</p>
              </div>
            </div>

            <div data-reveal style="--i:2">
              <div class="card-glow h-full rounded-xl p-6 bg-[var(--panel)] flex flex-col">
                <div class="flex items-baseline justify-between mb-6">
                  <span class="font-mono2 text-[34px] font-bold text-[rgba(249,127,181,0.85)] leading-none">6</span>
                  <span class="font-mono2 text-[10px] text-[var(--text-3)]">relation model</span>
                </div>
                <h3 class="font-mono2 text-[16px] font-semibold mb-1">六维关系模型</h3>
                <div class="text-[12px] text-[var(--signal-soft)] mb-5">随互动平滑生长</div>
                <div class="mt-auto grid grid-cols-2 gap-2">
                  <div class="flex items-center gap-2">
                    <div class="h-1.5 flex-1 rounded-full bg-[var(--border-soft)] overflow-hidden">
                      <div class="h-full rounded-full bg-gradient-to-r from-[rgba(249,127,181,0.35)] to-[var(--signal)]" style="width: 88%"></div>
                    </div>
                    <span class="text-[11px] text-[var(--text-2)] w-6">亲密</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <div class="h-1.5 flex-1 rounded-full bg-[var(--border-soft)] overflow-hidden">
                      <div class="h-full rounded-full bg-gradient-to-r from-[rgba(249,127,181,0.35)] to-[var(--signal)]" style="width: 79%"></div>
                    </div>
                    <span class="text-[11px] text-[var(--text-2)] w-6">信任</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <div class="h-1.5 flex-1 rounded-full bg-[var(--border-soft)] overflow-hidden">
                      <div class="h-full rounded-full bg-gradient-to-r from-[rgba(249,127,181,0.35)] to-[var(--signal)]" style="width: 70%"></div>
                    </div>
                    <span class="text-[11px] text-[var(--text-2)] w-6">依赖</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <div class="h-1.5 flex-1 rounded-full bg-[var(--border-soft)] overflow-hidden">
                      <div class="h-full rounded-full bg-gradient-to-r from-[rgba(249,127,181,0.35)] to-[var(--signal)]" style="width: 61%"></div>
                    </div>
                    <span class="text-[11px] text-[var(--text-2)] w-6">好感</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <div class="h-1.5 flex-1 rounded-full bg-[var(--border-soft)] overflow-hidden">
                      <div class="h-full rounded-full bg-gradient-to-r from-[rgba(249,127,181,0.35)] to-[var(--signal)]" style="width: 52%"></div>
                    </div>
                    <span class="text-[11px] text-[var(--text-2)] w-6">默契</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <div class="h-1.5 flex-1 rounded-full bg-[var(--border-soft)] overflow-hidden">
                      <div class="h-full rounded-full bg-gradient-to-r from-[rgba(249,127,181,0.35)] to-[var(--signal)]" style="width: 43%"></div>
                    </div>
                    <span class="text-[11px] text-[var(--text-2)] w-6">敬畏</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ============ Architecture ============ -->
      <section id="architecture" class="relative py-24 md:py-32 border-t border-[var(--border-soft)]">
        <div class="mx-auto max-w-7xl px-5 md:px-8">
          <div class="mb-12 md:mb-16">
            <div data-reveal style="--i:0">
              <div class="flex items-center gap-3 mb-5">
                <span class="font-mono2 text-[12px] font-semibold text-[var(--signal)]">03</span>
                <span class="h-px w-8 bg-[var(--border)]"></span>
                <span class="font-mono2 text-[11px] tracking-[0.18em] uppercase text-[var(--text-3)]">Architecture</span>
              </div>
            </div>
            <div data-reveal style="--i:1">
              <h2 class="text-[30px] md:text-[44px] leading-[1.15] font-bold tracking-[-0.015em] max-w-[18ch]">统一 AI 内核，频道只是适配层</h2>
            </div>
            <div data-reveal style="--i:2">
              <p class="mt-4 max-w-[58ch] text-[15px] leading-[1.8] text-[var(--text-2)]">请求流经过预处理、对话、后处理三段管线，角色运行时在每轮前后挂载——任何一个频道，得到的都是同一个「她」。</p>
            </div>
          </div>

          <div class="grid lg:grid-cols-[1.15fr_1fr] gap-6">
            <div data-reveal style="--i:0">
              <div class="card-glow rounded-xl p-7 md:p-9 h-full">
                <div class="font-mono2 text-[11px] tracking-[0.16em] text-[var(--text-3)] mb-8">REQUEST FLOW</div>
                <div class="flex flex-col items-stretch gap-0">
                  <div>
                    <div class="rounded-lg border px-4 py-3 font-mono2 text-[13px] flex items-center justify-between transition-colors border-[var(--border)] bg-[var(--panel-2)] text-[var(--text-2)]">
                      <span>Channel Adapter</span>
                      <span class="text-[10px] text-[var(--text-3)]">01</span>
                    </div>
                    <svg width="100%" height="26" class="block" aria-hidden="true">
                      <line x1="50%" y1="2" x2="50%" y2="24" stroke="#3a3f49" stroke-width="1.5" class="dash-flow"></line>
                      <polygon points="-3.5,19 3.5,19 0,25" fill="#3a3f49" style="transform:translateX(50%)"></polygon>
                    </svg>
                  </div>
                  <div>
                    <div class="rounded-lg border px-4 py-3 font-mono2 text-[13px] flex items-center justify-between transition-colors border-[var(--border)] bg-[var(--panel-2)] text-[var(--text-2)]">
                      <span>ChatRequest</span>
                      <span class="text-[10px] text-[var(--text-3)]">02</span>
                    </div>
                    <svg width="100%" height="26" class="block" aria-hidden="true">
                      <line x1="50%" y1="2" x2="50%" y2="24" stroke="#3a3f49" stroke-width="1.5" class="dash-flow"></line>
                      <polygon points="-3.5,19 3.5,19 0,25" fill="#3a3f49" style="transform:translateX(50%)"></polygon>
                    </svg>
                  </div>
                  <div>
                    <div class="rounded-lg border px-4 py-3 font-mono2 text-[13px] flex items-center justify-between transition-colors border-[var(--border)] bg-[var(--panel-2)] text-[var(--text-2)]">
                      <span>AI Pipeline</span>
                      <span class="text-[10px] text-[var(--text-3)]">03</span>
                    </div>
                    <svg width="100%" height="26" class="block" aria-hidden="true">
                      <line x1="50%" y1="2" x2="50%" y2="24" stroke="#3a3f49" stroke-width="1.5" class="dash-flow"></line>
                      <polygon points="-3.5,19 3.5,19 0,25" fill="#3a3f49" style="transform:translateX(50%)"></polygon>
                    </svg>
                  </div>
                  <div>
                    <div class="rounded-lg border px-4 py-3 font-mono2 text-[13px] flex items-center justify-between transition-colors border-[rgba(249,127,181,0.5)] bg-[rgba(249,127,181,0.07)] text-[var(--signal-soft)]">
                      <span>Character Runtime</span>
                      <span class="text-[10px] text-[var(--text-3)]">04</span>
                    </div>
                    <svg width="100%" height="26" class="block" aria-hidden="true">
                      <line x1="50%" y1="2" x2="50%" y2="24" stroke="#3a3f49" stroke-width="1.5" class="dash-flow"></line>
                      <polygon points="-3.5,19 3.5,19 0,25" fill="#3a3f49" style="transform:translateX(50%)"></polygon>
                    </svg>
                  </div>
                  <div>
                    <div class="rounded-lg border px-4 py-3 font-mono2 text-[13px] flex items-center justify-between transition-colors border-[var(--border)] bg-[var(--panel-2)] text-[var(--text-2)]">
                      <span>Model Adapter</span>
                      <span class="text-[10px] text-[var(--text-3)]">05</span>
                    </div>
                    <svg width="100%" height="26" class="block" aria-hidden="true">
                      <line x1="50%" y1="2" x2="50%" y2="24" stroke="rgba(249,127,181,0.6)" stroke-width="1.5" class="dash-flow"></line>
                      <polygon points="-3.5,19 3.5,19 0,25" fill="rgba(249,127,181,0.6)" style="transform:translateX(50%)"></polygon>
                    </svg>
                  </div>
                  <div>
                    <div class="rounded-lg border px-4 py-3 font-mono2 text-[13px] flex items-center justify-between transition-colors border-[var(--border)] bg-[var(--panel-2)] text-[var(--text-2)]">
                      <span>ChatResponse</span>
                      <span class="text-[10px] text-[var(--text-3)]">06</span>
                    </div>
                  </div>
                </div>
                <div class="mt-6 font-mono2 text-[11px] text-[var(--text-3)]">before_turn() → chat → after_turn() · 钩子全程挂载</div>
              </div>
            </div>

            <div class="flex flex-col gap-4">
              <div data-reveal style="--i:0">
                <div class="card-glow rounded-xl p-5 flex gap-4 items-start transition-colors hover:bg-[var(--panel-2)]">
                  <span class="font-mono2 text-[11px] text-[var(--signal)] mt-1 shrink-0">01</span>
                  <div>
                    <div class="font-mono2 text-[13.5px] font-semibold mb-1">core/ 不依赖频道层</div>
                    <p class="text-[13px] leading-[1.7] text-[var(--text-2)]">统一 AI 流水线只面向 ChatRequest / ChatResponse，与具体平台解耦。</p>
                  </div>
                </div>
              </div>
              <div data-reveal style="--i:1">
                <div class="card-glow rounded-xl p-5 flex gap-4 items-start transition-colors hover:bg-[var(--panel-2)]">
                  <span class="font-mono2 text-[11px] text-[var(--signal)] mt-1 shrink-0">02</span>
                  <div>
                    <div class="font-mono2 text-[13.5px] font-semibold mb-1">BaseChannelAdapter</div>
                    <p class="text-[13px] leading-[1.7] text-[var(--text-2)]">所有新频道都通过适配器接入，而不是直接调用模型。</p>
                  </div>
                </div>
              </div>
              <div data-reveal style="--i:2">
                <div class="card-glow rounded-xl p-5 flex gap-4 items-start transition-colors hover:bg-[var(--panel-2)]">
                  <span class="font-mono2 text-[11px] text-[var(--signal)] mt-1 shrink-0">03</span>
                  <div>
                    <div class="font-mono2 text-[13.5px] font-semibold mb-1">before / after turn</div>
                    <p class="text-[13px] leading-[1.7] text-[var(--text-2)]">角色逻辑通过钩子挂入流水线，情感与记忆随每轮对话更新。</p>
                  </div>
                </div>
              </div>
              <div data-reveal style="--i:2">
                <div class="code-block rounded-xl p-5 overflow-x-auto">
                  <div class="font-mono2 text-[11px] tracking-[0.16em] text-[var(--text-3)] mb-3">PROJECT TREE</div>
                  <pre class="font-mono2 text-[12px] leading-[1.75] text-[var(--text-2)]">bot.py
└── nbot/
    ├── core/        # 统一 AI 流水线
    ├── character/   # 情感运行时与关系模型
    ├── channels/    # QQ / Web / TG / 飞书适配
    ├── services/    # AI 客户端、工具、TTS/STT
    ├── plugins/     # 插件与技能系统
    ├── gateway/     # 消息总线 · 路由 · 去重
    ├── mcp/         # MCP Server（AI Agent 接口）
    └── web/         # Flask 蓝图 · Socket.IO · 后台</pre>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ============ MCP ============ -->
      <section id="mcp" class="relative py-24 md:py-32 border-t border-[var(--border-soft)] overflow-hidden">
        <div class="glow-orb absolute bottom-0 -right-48 w-[560px] h-[560px] pointer-events-none opacity-50"></div>
        <div class="relative mx-auto max-w-7xl px-5 md:px-8">
          <div class="mb-12 md:mb-16">
            <div data-reveal style="--i:0">
              <div class="flex items-center gap-3 mb-5">
                <span class="font-mono2 text-[12px] font-semibold text-[var(--signal)]">04</span>
                <span class="h-px w-8 bg-[var(--border)]"></span>
                <span class="font-mono2 text-[11px] tracking-[0.18em] uppercase text-[var(--text-3)]">Model Context Protocol</span>
              </div>
            </div>
            <div data-reveal style="--i:1">
              <h2 class="text-[30px] md:text-[44px] leading-[1.15] font-bold tracking-[-0.015em] max-w-[18ch]">让 AI Agent 直接操纵 Gateway</h2>
            </div>
            <div data-reveal style="--i:2">
              <p class="mt-4 max-w-[58ch] text-[15px] leading-[1.8] text-[var(--text-2)]">内置 MCP Server，把消息、事件、队列、节点等能力以标准协议暴露出去——Claude Code、Cursor、ChatGPT Agent 即刻接入。</p>
            </div>
          </div>

          <div class="grid lg:grid-cols-2 gap-6">
            <div data-reveal style="--i:0">
              <div class="code-block rounded-xl overflow-hidden h-full flex flex-col">
                <div class="flex items-center gap-1.5 px-4 py-3 border-b border-[var(--border-soft)]">
                  <span class="terminal-dots flex gap-1.5">
                    <span style="background: #f97066"></span>
                    <span style="background: #fdb022"></span>
                    <span style="background: #32d583"></span>
                  </span>
                  <span class="ml-2 font-mono2 text-[11px] text-[var(--text-3)]">mcp — zsh</span>
                </div>
                <div class="p-5 font-mono2 text-[12.5px] leading-[2] flex-1">
                  <div id="mcp-done"></div>
                  <div class="text-[var(--text-1)]">
                    <span class="text-[var(--signal)]">$</span> <span id="mcp-typed"></span><span class="cursor-blink text-[var(--signal-soft)]">▋</span>
                  </div>
                </div>
                <div class="border-t border-[var(--border-soft)] p-4">
                  <div class="flex items-center justify-between mb-2">
                    <span class="font-mono2 text-[11px] text-[var(--text-3)]">.mcp.json — Claude Code</span>
                    <button
                      type="button"
                      class="copy-btn inline-flex items-center justify-center rounded-md border border-[var(--border)] bg-[var(--panel-2)] p-1.5 text-[var(--text-3)] transition-colors hover:text-[var(--signal-soft)] hover:border-[rgba(249,127,181,0.4)]"
                      :data-copy="MCP_CONFIG"
                      aria-label="复制"
                    >
                      <span class="cb-icon-copy"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-copy" aria-hidden="true"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"></rect><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"></path></svg></span>
                      <span class="cb-icon-check hidden"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-check text-emerald-400" aria-hidden="true"><path d="M20 6 9 17l-5-5"></path></svg></span>
                    </button>
                  </div>
                  <pre class="font-mono2 text-[11.5px] leading-[1.7] text-[var(--text-2)] overflow-x-auto">{{ MCP_CONFIG }}</pre>
                </div>
              </div>
            </div>

            <div data-reveal style="--i:1">
              <div class="card-glow rounded-xl p-6 h-full">
                <div class="flex items-center justify-between mb-5">
                  <span class="font-mono2 text-[11px] tracking-[0.16em] text-[var(--text-3)]">AVAILABLE TOOLS</span>
                  <span class="font-mono2 text-[11px] text-[var(--signal-soft)]">13 tools · 3 resources · 3 prompts</span>
                </div>
                <div class="flex flex-col divide-y divide-[var(--border-soft)]">
                  <div class="flex items-center gap-3 py-2.5 group">
                    <code class="font-mono2 text-[12px] text-[var(--text-1)] group-hover:text-[var(--signal-soft)] transition-colors">gateway_get_status</code>
                    <span class="text-[12px] text-[var(--text-3)] ml-auto hidden sm:block">Gateway 健康状态</span>
                    <span class="font-mono2 text-[10px] px-1.5 py-0.5 rounded border text-emerald-400 border-emerald-400/30 bg-emerald-400/5">只读</span>
                  </div>
                  <div class="flex items-center gap-3 py-2.5 group">
                    <code class="font-mono2 text-[12px] text-[var(--text-1)] group-hover:text-[var(--signal-soft)] transition-colors">gateway_get_stats</code>
                    <span class="text-[12px] text-[var(--text-3)] ml-auto hidden sm:block">事件 / 投递 / 去重统计</span>
                    <span class="font-mono2 text-[10px] px-1.5 py-0.5 rounded border text-emerald-400 border-emerald-400/30 bg-emerald-400/5">只读</span>
                  </div>
                  <div class="flex items-center gap-3 py-2.5 group">
                    <code class="font-mono2 text-[12px] text-[var(--text-1)] group-hover:text-[var(--signal-soft)] transition-colors">gateway_query_trace</code>
                    <span class="text-[12px] text-[var(--text-3)] ml-auto hidden sm:block">查询 trace 完整链路</span>
                    <span class="font-mono2 text-[10px] px-1.5 py-0.5 rounded border text-emerald-400 border-emerald-400/30 bg-emerald-400/5">只读</span>
                  </div>
                  <div class="flex items-center gap-3 py-2.5 group">
                    <code class="font-mono2 text-[12px] text-[var(--text-1)] group-hover:text-[var(--signal-soft)] transition-colors">gateway_query_events</code>
                    <span class="text-[12px] text-[var(--text-3)] ml-auto hidden sm:block">按条件查询事件</span>
                    <span class="font-mono2 text-[10px] px-1.5 py-0.5 rounded border text-emerald-400 border-emerald-400/30 bg-emerald-400/5">只读</span>
                  </div>
                  <div class="flex items-center gap-3 py-2.5 group">
                    <code class="font-mono2 text-[12px] text-[var(--text-1)] group-hover:text-[var(--signal-soft)] transition-colors">gateway_get_queue_stats</code>
                    <span class="text-[12px] text-[var(--text-3)] ml-auto hidden sm:block">队列状态</span>
                    <span class="font-mono2 text-[10px] px-1.5 py-0.5 rounded border text-emerald-400 border-emerald-400/30 bg-emerald-400/5">只读</span>
                  </div>
                  <div class="flex items-center gap-3 py-2.5 group">
                    <code class="font-mono2 text-[12px] text-[var(--text-1)] group-hover:text-[var(--signal-soft)] transition-colors">gateway_list_nodes</code>
                    <span class="text-[12px] text-[var(--text-3)] ml-auto hidden sm:block">节点列表</span>
                    <span class="font-mono2 text-[10px] px-1.5 py-0.5 rounded border text-emerald-400 border-emerald-400/30 bg-emerald-400/5">只读</span>
                  </div>
                  <div class="flex items-center gap-3 py-2.5 group">
                    <code class="font-mono2 text-[12px] text-[var(--text-1)] group-hover:text-[var(--signal-soft)] transition-colors">gateway_receive_message</code>
                    <span class="text-[12px] text-[var(--text-3)] ml-auto hidden sm:block">模拟频道消息</span>
                    <span class="font-mono2 text-[10px] px-1.5 py-0.5 rounded border text-amber-300 border-amber-300/30 bg-amber-300/5">操作</span>
                  </div>
                  <div class="flex items-center gap-3 py-2.5 group">
                    <code class="font-mono2 text-[12px] text-[var(--text-1)] group-hover:text-[var(--signal-soft)] transition-colors">gateway_submit_internal_task</code>
                    <span class="text-[12px] text-[var(--text-3)] ml-auto hidden sm:block">触发内部任务</span>
                    <span class="font-mono2 text-[10px] px-1.5 py-0.5 rounded border text-amber-300 border-amber-300/30 bg-amber-300/5">操作</span>
                  </div>
                  <div class="flex items-center gap-3 py-2.5 group">
                    <code class="font-mono2 text-[12px] text-[var(--text-1)] group-hover:text-[var(--signal-soft)] transition-colors">gateway_send_message</code>
                    <span class="text-[12px] text-[var(--text-3)] ml-auto hidden sm:block">发送真实消息</span>
                    <span class="font-mono2 text-[10px] px-1.5 py-0.5 rounded border text-rose-400 border-rose-400/30 bg-rose-400/5">高危</span>
                  </div>
                  <div class="flex items-center gap-3 py-2.5 group">
                    <code class="font-mono2 text-[12px] text-[var(--text-1)] group-hover:text-[var(--signal-soft)] transition-colors">gateway_retry_dead_letter</code>
                    <span class="text-[12px] text-[var(--text-3)] ml-auto hidden sm:block">重试死信</span>
                    <span class="font-mono2 text-[10px] px-1.5 py-0.5 rounded border text-rose-400 border-rose-400/30 bg-rose-400/5">高危</span>
                  </div>
                </div>
                <p class="mt-4 text-[12px] leading-[1.7] text-[var(--text-3)]">高危能力默认关闭，支持审计日志与确认机制；传输支持 stdio 本地与 streamable-http 远程两种模式。</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ============ Quick Start ============ -->
      <section id="quickstart" class="relative py-24 md:py-32 border-t border-[var(--border-soft)]">
        <div class="hero-grid absolute inset-0 pointer-events-none opacity-60"></div>
        <div class="relative mx-auto max-w-7xl px-5 md:px-8">
          <div class="mb-12 md:mb-16">
            <div data-reveal style="--i:0">
              <div class="flex items-center gap-3 mb-5">
                <span class="font-mono2 text-[12px] font-semibold text-[var(--signal)]">05</span>
                <span class="h-px w-8 bg-[var(--border)]"></span>
                <span class="font-mono2 text-[11px] tracking-[0.18em] uppercase text-[var(--text-3)]">Quick Start</span>
              </div>
            </div>
            <div data-reveal style="--i:1">
              <h2 class="text-[30px] md:text-[44px] leading-[1.15] font-bold tracking-[-0.015em] max-w-[18ch]">三分钟，让她上线</h2>
            </div>
            <div data-reveal style="--i:2">
              <p class="mt-4 max-w-[58ch] text-[15px] leading-[1.8] text-[var(--text-2)]">只需要 Python 3.10+ 与一个 OpenAI 兼容的 API。没有 QQ 配置时，项目可以仅以 Web 模式运行。</p>
            </div>
          </div>

          <div class="grid lg:grid-cols-[1.2fr_1fr] gap-6">
            <div data-reveal style="--i:0">
              <div class="code-block rounded-xl overflow-hidden">
                <div class="flex items-center gap-1 px-3 pt-3 border-b border-[var(--border-soft)]">
                  <button
                    type="button"
                    class="flex items-center gap-2 px-4 py-2.5 text-[13px] font-medium rounded-t-lg border-b-2 transition-colors"
                    :class="tab === 'src'
                      ? 'text-[var(--signal-soft)] border-[var(--signal)] bg-[rgba(249,127,181,0.05)]'
                      : 'text-[var(--text-3)] border-transparent hover:text-[var(--text-2)]'"
                    @click="tab = 'src'"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-file-code-corner" aria-hidden="true"><path d="M4 12.15V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.706.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2h-3.35"></path><path d="M14 2v5a1 1 0 0 0 1 1h5"></path><path d="m5 16-3 3 3 3"></path><path d="m9 22 3-3-3-3"></path></svg>
                    源码安装
                  </button>
                  <button
                    type="button"
                    class="flex items-center gap-2 px-4 py-2.5 text-[13px] font-medium rounded-t-lg border-b-2 transition-colors"
                    :class="tab === 'docker'
                      ? 'text-[var(--signal-soft)] border-[var(--signal)] bg-[rgba(249,127,181,0.05)]'
                      : 'text-[var(--text-3)] border-transparent hover:text-[var(--text-2)]'"
                    @click="tab = 'docker'"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-container" aria-hidden="true"><path d="M22 7.7c0-.6-.4-1.2-.8-1.5l-6.3-3.9a1.72 1.72 0 0 0-1.7 0l-10.3 6c-.5.2-.9.8-.9 1.4v6.6c0 .5.4 1.2.8 1.5l6.3 3.9a1.72 1.72 0 0 0 1.7 0l10.3-6c.5-.3.9-1 .9-1.5Z"></path><path d="M10 21.9V14L2.1 9.1"></path><path d="m10 14 11.9-6.9"></path><path d="M14 19.8v-8.1"></path><path d="M18 17.5V9.4"></path></svg>
                    Docker 部署
                  </button>
                  <button
                    type="button"
                    class="copy-btn inline-flex items-center justify-center rounded-md border border-[var(--border)] bg-[var(--panel-2)] p-1.5 text-[var(--text-3)] transition-colors hover:text-[var(--signal-soft)] hover:border-[rgba(249,127,181,0.4)] ml-auto mb-1.5"
                    :data-copy="tab === 'src' ? SRC_CODE : DOCKER_CODE"
                    aria-label="复制"
                  >
                    <span class="cb-icon-copy"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-copy" aria-hidden="true"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"></rect><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"></path></svg></span>
                    <span class="cb-icon-check hidden"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-check text-emerald-400" aria-hidden="true"><path d="M20 6 9 17l-5-5"></path></svg></span>
                  </button>
                </div>
                <pre v-show="tab === 'src'" class="p-5 font-mono2 text-[12.5px] leading-[1.8] text-[var(--text-2)] overflow-x-auto min-h-[340px]">{{ SRC_CODE }}</pre>
                <pre v-show="tab === 'docker'" class="p-5 font-mono2 text-[12.5px] leading-[1.8] text-[var(--text-2)] overflow-x-auto min-h-[340px]">{{ DOCKER_CODE }}</pre>
              </div>
            </div>

            <div class="flex flex-col gap-4">
              <div data-reveal style="--i:0">
                <div class="card-glow rounded-xl p-5 flex gap-4 items-start transition-colors hover:bg-[var(--panel-2)]">
                  <span class="font-mono2 text-[20px] font-bold text-[var(--signal)] leading-none mt-0.5">01</span>
                  <div>
                    <div class="text-[15px] font-semibold mb-1">打开 Web 控制台</div>
                    <p class="text-[13px] leading-[1.7] text-[var(--text-2)]">访问 :5000，用 WEB_PASSWORD 登录，可视化配置你的第一个模型。</p>
                  </div>
                </div>
              </div>
              <div data-reveal style="--i:1">
                <div class="card-glow rounded-xl p-5 flex gap-4 items-start transition-colors hover:bg-[var(--panel-2)]">
                  <span class="font-mono2 text-[20px] font-bold text-[var(--signal)] leading-none mt-0.5">02</span>
                  <div>
                    <div class="text-[15px] font-semibold mb-1">创建角色卡</div>
                    <p class="text-[13px] leading-[1.7] text-[var(--text-2)]">在「人格设置」中创建、编辑或导入角色卡，设定语气与边界。</p>
                  </div>
                </div>
              </div>
              <div data-reveal style="--i:2">
                <div class="card-glow rounded-xl p-5 flex gap-4 items-start transition-colors hover:bg-[var(--panel-2)]">
                  <span class="font-mono2 text-[20px] font-bold text-[var(--signal)] leading-none mt-0.5">03</span>
                  <div>
                    <div class="text-[15px] font-semibold mb-1">接入频道</div>
                    <p class="text-[13px] leading-[1.7] text-[var(--text-2)]">部署 NapCatQQ 或配置 Telegram / 飞书，让角色在你所在的平台上线。</p>
                  </div>
                </div>
              </div>
              <div data-reveal style="--i:3">
                <a :href="withBase('/guide/quick-start')" class="group flex items-center justify-between rounded-xl border border-[rgba(249,127,181,0.4)] bg-[rgba(249,127,181,0.06)] px-6 py-4 transition-colors hover:bg-[rgba(249,127,181,0.12)]">
                  <div class="flex items-center gap-2 text-[15px] font-semibold text-[var(--signal-soft)]">
                    <svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-book-open" aria-hidden="true"><path d="M12 7v14"></path><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"></path></svg>
                    阅读完整文档
                  </div>
                  <span class="font-mono2 text-[18px] text-[var(--signal-soft)] transition-transform group-hover:translate-x-1">→</span>
                </a>
              </div>
              <div data-reveal style="--i:3">
                <a href="https://github.com/asukaneko/nekobot" target="_blank" rel="noreferrer" class="cta-breathe group flex items-center justify-between rounded-xl bg-[var(--signal-strong)] px-6 py-5 text-[#1a0b12] transition-transform hover:scale-[1.01] active:scale-[0.99]">
                  <div>
                    <div class="text-[16px] font-bold flex items-center gap-2">
                      <svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-rocket" aria-hidden="true"><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"></path><path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"></path><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"></path><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"></path></svg>
                      前往 GitHub 获取源码
                    </div>
                    <div class="text-[12px] opacity-80 mt-0.5">完整部署指南 · Compose · HTTPS · 升级说明</div>
                  </div>
                  <span class="font-mono2 text-[20px] transition-transform group-hover:translate-x-1">→</span>
                </a>
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>

    <!-- ============ Footer ============ -->
    <footer class="border-t border-[var(--border-soft)] bg-[#0c0d10]">
      <div class="mx-auto max-w-7xl px-5 md:px-8 pt-16 pb-10">
        <div class="grid md:grid-cols-[1.3fr_repeat(3,1fr)] gap-10">
          <div>
            <div class="flex items-center gap-3 mb-4">
              <img :src="withBase('/neko.png')" alt="NekoBot" class="w-9 h-9 rounded-lg" />
              <span class="font-mono2 font-semibold text-[17px]">
                Neko<span class="text-[var(--signal)]">Bot</span>
              </span>
            </div>
            <p class="text-[13px] leading-[1.8] text-[var(--text-3)] max-w-[36ch]">
              面向 Web 的多频道 AI 角色扮演系统。
              <br />
              Cute. Sleepy. <span class="text-[var(--signal-soft)]">Smart.</span>
            </p>
            <a href="https://github.com/asukaneko/nekobot" target="_blank" rel="noreferrer" class="mt-5 inline-flex items-center gap-2 text-[13px] text-[var(--text-2)] hover:text-white transition-colors">
              <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-github" aria-hidden="true"><path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4"></path><path d="M9 18c-4.51 2-5-2-7-2"></path></svg>
              asukaneko / nekobot
            </a>
          </div>
          <div>
            <div class="font-mono2 text-[11px] tracking-[0.16em] uppercase text-[var(--text-3)] mb-4">项目</div>
            <ul class="flex flex-col gap-2.5">
              <li><a href="https://github.com/asukaneko/nekobot" target="_blank" rel="noreferrer" class="text-[13.5px] text-[var(--text-2)] hover:text-[var(--signal-soft)] transition-colors">GitHub 仓库</a></li>
              <li><a href="https://github.com/asukaneko/nekobot-android" target="_blank" rel="noreferrer" class="text-[13.5px] text-[var(--text-2)] hover:text-[var(--signal-soft)] transition-colors">Android 客户端</a></li>
              <li><a href="https://github.com/asukaneko/nekobot/blob/main/docs/CHANGELOG.md" target="_blank" rel="noreferrer" class="text-[13.5px] text-[var(--text-2)] hover:text-[var(--signal-soft)] transition-colors">更新记录</a></li>
            </ul>
          </div>
          <div>
            <div class="font-mono2 text-[11px] tracking-[0.16em] uppercase text-[var(--text-3)] mb-4">文档</div>
            <ul class="flex flex-col gap-2.5">
              <li><a :href="withBase('/guide/quick-start')" class="text-[13.5px] text-[var(--text-2)] hover:text-[var(--signal-soft)] transition-colors">快速开始</a></li>
              <li><a :href="withBase('/guide/docker-deploy')" class="text-[13.5px] text-[var(--text-2)] hover:text-[var(--signal-soft)] transition-colors">Docker 部署</a></li>
              <li><a :href="withBase('/guide/commands')" class="text-[13.5px] text-[var(--text-2)] hover:text-[var(--signal-soft)] transition-colors">所有命令</a></li>
              <li><a :href="withBase('/guide/advanced/mcp-integration')" class="text-[13.5px] text-[var(--text-2)] hover:text-[var(--signal-soft)] transition-colors">MCP 文档</a></li>
            </ul>
          </div>
          <div>
            <div class="font-mono2 text-[11px] tracking-[0.16em] uppercase text-[var(--text-3)] mb-4">生态</div>
            <ul class="flex flex-col gap-2.5">
              <li><a href="https://github.com/NapNeko/NapCatQQ" target="_blank" rel="noreferrer" class="text-[13.5px] text-[var(--text-2)] hover:text-[var(--signal-soft)] transition-colors">NapCatQQ</a></li>
              <li><a href="https://modelcontextprotocol.io" target="_blank" rel="noreferrer" class="text-[13.5px] text-[var(--text-2)] hover:text-[var(--signal-soft)] transition-colors">Model Context Protocol</a></li>
              <li><a href="https://github.com/huan-yp/ncatbot" target="_blank" rel="noreferrer" class="text-[13.5px] text-[var(--text-2)] hover:text-[var(--signal-soft)] transition-colors">ncatbot</a></li>
            </ul>
          </div>
        </div>
        <div class="mt-14 pt-6 border-t border-[var(--border-soft)] flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <span class="font-mono2 text-[11px] text-[var(--text-3)]">© 2026 asukaneko · Released under the MIT License</span>
          <span class="font-mono2 text-[11px] text-[var(--text-3)]">neko --help → be kind · stay curious · automate the rest · have fun</span>
        </div>
      </div>
    </footer>
  </div>
</template>
