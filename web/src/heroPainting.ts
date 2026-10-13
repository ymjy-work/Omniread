/**
 * 门厅首屏的程序化画布：**零图片素材**，笔触由「宽度沿程渐变的带状多边形」堆出来。
 *
 * 三条纪律，违反任何一条都会让画面一眼看出是程序画的：
 *
 * 1. **不用恒定 `lineWidth`**：真实笔画的宽度是变的（起笔重、行笔饱满、收笔细），
 *    所以不 `stroke()`，而是沿路径算出左右轮廓、填一个带状多边形。
 * 2. **一切随机都走固定种子**：布局、星点、飞白位置都在一次绘制里定死。
 *    逐帧 `Math.random()` 会让画面疯狂抖动——这是这套东西最容易犯也最难自查的错。
 * 3. **深底 + 亮笔必须用加色混合（`lighter`）**：光叠光才累积成辉光；用 `source-over`
 *    把亮色叠在深底上只能得到平的灰块。
 *
 * 画是**一次性静态绘制**（不进 rAF），所以任何时刻截图都得到同一张画——
 * 顺带让 headless 核对变得确定，不用跟抓帧竞态打架。
 *
 * 画成**发光的**夜空（星云、密星、发光圆相）：遮罩是深的，深遮罩只有「拨开看见光」
 * 才读得出来，暗底上拨开暗雾等于什么也没发生。
 */

/** 三种「材料」：`INK` 是夜空底，`GLOW` / `CY` 是加光（lighter）。**不要混用。** */
const INK = '3, 12, 16'
const GLOW = '206, 248, 246'
/**
 * 画面主色：**跟页面的强调色走**（现在是紫罗兰）。换色只改这一个常量——
 * 加色混合下换色相是安全的（光还是光），但**混合方式不能跟着换**：
 * 深底 + 亮笔必须 `lighter`，用 `source-over` 叠亮色只会得到平的灰块。
 */
const CY = '150, 128, 255'

/** 固定种子伪随机（mulberry32）。**画面里一个 `Math.random()` 都不该有。** */
function seeded(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** 笔触原语：沿路径生成宽度渐变的带状多边形。`widthAt(u)` 给该处的半宽。 */
function ribbon(
  ctx: CanvasRenderingContext2D,
  pts: readonly (readonly [number, number])[],
  widthAt: (u: number) => number,
  fill: string,
  composite: GlobalCompositeOperation = 'lighter'
): void {
  const n = pts.length
  if (n < 2) return
  const left: [number, number][] = []
  const right: [number, number][] = []
  for (let i = 0; i < n; i++) {
    const p = pts[i]
    const q = pts[Math.min(n - 1, i + 1)]
    const r = pts[Math.max(0, i - 1)]
    const dx = q[0] - r[0]
    const dy = q[1] - r[1]
    const len = Math.sqrt(dx * dx + dy * dy) || 1
    const nx = -dy / len
    const ny = dx / len
    const hw = Math.max(0.2, widthAt(i / (n - 1)))
    left.push([p[0] + nx * hw, p[1] + ny * hw])
    right.push([p[0] - nx * hw, p[1] - ny * hw])
  }
  ctx.save()
  ctx.globalCompositeOperation = composite
  ctx.beginPath()
  ctx.moveTo(left[0][0], left[0][1])
  for (let i = 1; i < n; i++) ctx.lineTo(left[i][0], left[i][1])
  for (let i = n - 1; i >= 0; i--) ctx.lineTo(right[i][0], right[i][1])
  ctx.closePath()
  ctx.fillStyle = fill
  ctx.fill()
  ctx.restore()
}

/** 宽度包络：两端收细，中段带「呼吸」——等宽的笔道一眼假。 */
function envelope(head: number, tail: number): (u: number) => number {
  return (u) =>
    Math.min(
      Math.pow(Math.min(1, u / Math.max(0.001, head)), 0.62),
      Math.pow(Math.min(1, (1 - u) / Math.max(0.001, tail)), 0.62)
    )
}

/** 一支笔：带状笔道 + 可选飞白（中段用 `destination-out` 擦出缝）+ 沿笔道撒星。 */
function brush(
  ctx: CanvasRenderingContext2D,
  color: string,
  rand: () => number
): (
  pts: readonly (readonly [number, number])[],
  wMax: number,
  alpha: number,
  opt?: { head?: number; tail?: number; dry?: boolean }
) => void {
  return (pts, wMax, alpha, opt = {}) => {
    const env = envelope(opt.head ?? 0.28, opt.tail ?? 0.68)
    const widthAt = (u: number): number =>
      wMax * 0.5 * Math.max(0.07, env(u)) * (0.86 + 0.14 * Math.sin(u * 7.3))

    ribbon(ctx, pts, widthAt, `rgba(${color}, ${alpha.toFixed(3)})`)

    if (opt.dry) {
      const from = 0.16 + rand() * 0.2
      const to = 0.6 + rand() * 0.26
      const sub = pts.slice(
        Math.floor(pts.length * from),
        Math.max(Math.floor(pts.length * from) + 3, Math.floor(pts.length * to))
      )
      ribbon(
        ctx,
        sub,
        (u) => wMax * 0.13 * Math.max(0.1, Math.sin(u * Math.PI)),
        `rgba(0, 0, 0, ${(0.38 + rand() * 0.34).toFixed(3)})`,
        'destination-out'
      )
    }

    // 沿笔道撒星：深底上只把笔道调亮，会得到一条发亮的带子；撒上点才读得出「这是用光画的」
    const count = Math.max(8, Math.round(pts.length * 0.8))
    for (let s = 0; s < count; s++) {
      const t = rand()
      const p = pts[Math.min(pts.length - 1, Math.floor(t * (pts.length - 1)))]
      const w = Math.max(0.6, widthAt(t))
      ctx.fillStyle = `rgba(${GLOW}, ${(0.24 + rand() * 0.76).toFixed(3)})`
      const size = rand() < 0.12 ? 2 : 1
      ctx.fillRect(p[0] + (rand() - 0.5) * w * 1.5, p[1] + (rand() - 0.5) * w * 1.5, size, size)
    }
  }
}

/** 一圈环上的点（半径带正弦扰动，避免正圆）。 */
function ringPoints(
  cx: number,
  cy: number,
  radius: number,
  rand: () => number,
  from: number,
  to: number,
  steps: number
): [number, number][] {
  const pts: [number, number][] = []
  for (let i = 0; i <= steps; i++) {
    const a = from + (to - from) * (i / steps)
    const rr = radius * (1 + Math.sin(a * 2.1) * 0.035 + (rand() - 0.5) * 0.018)
    pts.push([cx + Math.cos(a) * rr * 1.04, cy + Math.sin(a) * rr])
  }
  return pts
}

export interface HeroPaintingOptions {
  width: number
  height: number
  /** 每张画一个种子：同一个种子永远得到同一张画（截图核对的前提）。 */
  seed?: number
  /**
   * 画不画**静态**流星。false 时留着天空其余部分（星云 / 密星 / 圆相 / 云海），
   * 流星改由 `createMeteorField` 逐帧画——两套流星同时出现会显得画面在下雨。
   */
  meteors?: boolean
}

/**
 * 画首屏：**发光的夜空**——星云、密星、几道流星、一笔未闭合的发光圆相、下缘云海。
 * 构成定成这一个概念就够，堆三种风格反而散。
 *
 * 「发光」不是修辞：深色遮罩要能「拨开」，底下必须有光可露。
 */
export function paintHero(canvas: HTMLCanvasElement, options: HeroPaintingOptions): void {
  const { width: w, height: h } = options
  const rand = seeded(options.seed ?? 20261011)
  const ctx = canvas.getContext('2d')
  if (!ctx || w <= 0 || h <= 0) return

  // **不动 transform**：dpr 缩放由调用方设好，下面一律按 CSS 像素作画。
  // 在这里 setTransform(1,0,0,1,0,0) 会把 dpr 抹掉，高分屏上就只画出左上角四分之一（踩过）。
  ctx.globalCompositeOperation = 'source-over'
  ctx.clearRect(0, 0, w, h)

  // 底色：上深下更深，中间偏青。渐变只在尺寸变化时建一次（循环里 new 渐变是明确的性能坑）
  const base = ctx.createLinearGradient(0, 0, 0, h)
  base.addColorStop(0, 'rgba(7, 24, 29, 1)')
  base.addColorStop(0.55, 'rgba(5, 16, 21, 1)')
  base.addColorStop(1, `rgba(${INK}, 1)`)
  ctx.fillStyle = base
  ctx.fillRect(0, 0, w, h)

  // 星云：三团青晕，位置由种子定。够亮才叫「发光的夜空」——这是遮罩拨开后要露出来的东西
  ctx.globalCompositeOperation = 'lighter'
  const nebulae: [number, number, number, number][] = [
    [w * 0.74, h * 0.3, Math.max(w, h) * 0.52, 0.3],
    [w * 0.16, h * 0.62, Math.max(w, h) * 0.44, 0.17],
    [w * 0.46, h * 0.04, Math.max(w, h) * 0.36, 0.12]
  ]
  for (const [cx, cy, r, alpha] of nebulae) {
    const halo = ctx.createRadialGradient(cx, cy, 0, cx, cy, r)
    halo.addColorStop(0, `rgba(${CY}, ${alpha})`)
    halo.addColorStop(0.55, `rgba(${CY}, ${(alpha * 0.32).toFixed(3)})`)
    halo.addColorStop(1, `rgba(${CY}, 0)`)
    ctx.fillStyle = halo
    ctx.fillRect(cx - r, cy - r, r * 2, r * 2)
  }

  const pen = brush(ctx, GLOW, rand)

  // 散星：幂律拉开层次——多数很暗、极少数很亮，等概率会得到一片均匀的噪点
  const stars = Math.round((w * h) / 2000)
  for (let i = 0; i < stars; i++) {
    const x = rand() * w
    const y = rand() * h * 0.9
    const r = rand()
    const alpha = Math.pow(r, 1.7) * 0.98 + 0.08
    const size = r > 0.96 ? 2 : 1
    ctx.fillStyle = r > 0.88 ? `rgba(${GLOW}, ${alpha.toFixed(3)})` : `rgba(${CY}, ${alpha.toFixed(3)})`
    ctx.fillRect(x, y, size, size)
  }

  // 流星：尾部拖长（head 小 / tail 大 = 一头尖一头虚），头部点一个亮点。
  // `meteors: false` 时整段跳过——那一版由 createMeteorField 逐帧画会动的流星
  if (options.meteors !== false) {
    const meteors = 5
    for (let i = 0; i < meteors; i++) {
      const startX = w * (0.08 + rand() * 0.8)
      const startY = h * (0.05 + rand() * 0.44)
      const len = h * (0.16 + rand() * 0.24)
      const angle = 0.35 + rand() * 0.3
      // 点序是**从尾到头**：u=1 那端（左下）是头。尾迹要「尾细头粗」，
      // 亮点也必须放在头那一端——画在收细的那头看起来就是倒着飞的（动画版踩过同一个坑）
      const pts: [number, number][] = []
      const steps = 54
      for (let s = 0; s <= steps; s++) {
        const u = s / steps
        pts.push([
          startX - Math.cos(angle) * len * u + Math.sin(u * 5.2) * 6,
          startY + Math.sin(angle) * len * u
        ])
      }
      pen(pts, 7 + rand() * 3.4, 0.2 + rand() * 0.1, { head: 0.9, tail: 0.05 })
      const head = pts[steps]
      ctx.beginPath()
      ctx.arc(head[0], head[1], 2 + rand() * 1.4, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(${GLOW}, 1)`
      ctx.fill()
    }
  }

  // 圆相：一笔未闭合的环，起笔最重、收笔虚掉。
  // **半宽按半径的百分之几取**——取到半径的一半，画出来是个实心圆盘（踩过），环之所以是环全靠这条细。
  const ringRadius = Math.min(w, h) * (w < 720 ? 0.19 : 0.155)
  const cx = w * (w < 720 ? 0.5 : 0.815)
  const cy = h * (w < 720 ? 0.28 : 0.3)
  const ringPts = ringPoints(cx, cy, ringRadius, rand, -0.55, Math.PI * 2 - 0.8, 72)
  const ringEnv = envelope(0.2, 0.5)
  const ringWidth = (scale: number) => (u: number) =>
    ringRadius * 0.055 * scale * Math.max(0.07, ringEnv(u)) * (0.86 + 0.14 * Math.sin(u * 7.3))

  // 宽而淡的一层当晕，再叠一层窄而亮的当本体（禁用 shadowBlur，辉光只能这么叠）
  ribbon(ctx, ringPts, ringWidth(5.2), `rgba(${CY}, 0.1)`)
  ribbon(ctx, ringPts, ringWidth(1), `rgba(${CY}, 0.9)`)

  // 收笔方向甩出几点墨，环内一层极淡的晕
  for (let i = 0; i < 20; i++) {
    const d = ringRadius * (0.1 + rand() * 0.45)
    const a = Math.PI * 2 - 0.8 + (rand() - 0.5) * 0.5
    ctx.fillStyle = `rgba(${CY}, ${(0.16 + rand() * 0.5).toFixed(3)})`
    ctx.fillRect(cx + Math.cos(a) * (ringRadius + d), cy + Math.sin(a) * (ringRadius + d), 1, 1)
  }
  const inner = ctx.createRadialGradient(cx, cy, 0, cx, cy, ringRadius * 0.95)
  inner.addColorStop(0, `rgba(${CY}, 0.1)`)
  inner.addColorStop(0.7, `rgba(${CY}, 0.04)`)
  inner.addColorStop(1, `rgba(${CY}, 0)`)
  ctx.fillStyle = inner
  ctx.fillRect(cx - ringRadius, cy - ringRadius, ringRadius * 2, ringRadius * 2)

  // 云海：下缘四道横向弱笔触，越靠上越宽越淡（把视线往标题上推）
  for (let i = 0; i < 4; i++) {
    const y = h * (0.78 + i * 0.06)
    const pts: [number, number][] = []
    const steps = 40
    for (let s = 0; s <= steps; s++) {
      const u = s / steps
      pts.push([w * u, y + Math.sin(u * 6.1 + i * 1.7) * (10 + i * 4) + (rand() - 0.5) * 5])
    }
    pen(pts, 26 + i * 12, 0.075 + i * 0.02, { head: 0.45, tail: 0.45 })
  }

  ctx.globalCompositeOperation = 'source-over'
}

/* ============================================================================
   遮罩揭示：雾盖住画，指针划过「拨开」，停手自己合拢。
   ========================================================================== */

/** 遮罩色（深）与浓度；浓度越高默认越暗、擦开的落差越大。 */
const VEIL_RGB = '4, 13, 17'
const VEIL = 0.68

/**
 * 墨点：初始半径 / 半径上限 / 存活时长（ms）/ 沿轨迹取点间距 / 同时存活上限 / 轮廓顶点数。
 *
 * `MAX_STAMPS` 是**每帧成本的总闸**：存活多少点，`draw` 里就画多少次多边形。
 * 参考站点（MiMo Code 官网）用的是 160，这里跟它对齐——原来的 420 在快速划动时
 * 每帧要填两份（擦 + 补光）八百多次。
 */
const R_START = 8
const R_END = 132
const LIFETIME = 520
const STAMP_STEP = 12
const MAX_STAMPS = 160
const SEGS = 32

interface Stamp {
  x: number
  y: number
  born: number
  rmax: number
  /** 一次算好存住：逐帧重算会让墨点边缘高频噪闪 */
  verts: number[]
}

export interface RevealController {
  resize(): void
  /** 跟着指针走：内部按 `STAMP_STEP` 插值补点，所以拖多快都是一条连续的擦痕。 */
  move(x: number, y: number): void
  /**
   * 指针进入首屏时调一次，把「上一个位置」忘掉。
   * 不重置的话：鼠标移出窗口、从另一侧回来时，第一条 `move` 会从**旧位置**插值过来，
   * 在画面上拉一道横穿的长痕（参考站点是在 `mouseenter` 里重置的）。
   */
  enter(): void
  stop(): void
}

/**
 * 遮罩揭示（技能里的签名交互，照配方复刻）。
 *
 * 机制：遮罩 canvas 上**每帧重铺整片遮罩**，指针划过的轨迹上留下一个个**各自扩张并淡出**的墨点，
 * 把遮罩擦开露出下面的画。所以「愈合」不是把擦掉的地方补回来，而是**墨点自己过期**——
 * 没有累积，也就不会出现「越划越黑」那种单向退化。
 *
 * 三条容易做错的：
 *
 * - **墨点不能用正圆**：正圆一眼就是程序画的（拖出来是一串圆点）。用三个正弦叠加扰动半径的
 *   多边形，加上沿法线的抖动，才像手抹过。
 * - **一次 pointermove 可能跨上百像素**：必须沿轨迹插值补点，否则快速划动只剩几个孤立的圆。
 * - **深色遮罩要「减光 + 加光」两趟**：遮罩只会减光，暗底上单靠擦除几乎看不出揭示
 *   （实测：擦掉的区域比周围还暗，等于没擦）。擦完沿同一条轨迹补一层加色的光，
 *   「拨开」才读得出是**露出光**而不是**抹掉一层**。
 */
export function createReveal(canvas: HTMLCanvasElement, options: { seed?: number } = {}): RevealController {
  const ctx = canvas.getContext('2d')
  const rand = seeded(options.seed ?? 4242)
  let width = 0
  let dpr = 1
  let raf = 0
  let running = false
  /** 遮罩是否已经铺好：没有存活墨点时不必每帧整片重填 */
  let veilFilled = false
  let stamps: Stamp[] = []
  let lastX: number | null = null
  let lastY: number | null = null
  /** 单位半径的渐变：**只建一次**，靠 translate/scale 复用（每个墨点各建一个是明确的性能坑） */
  let dotGrad: CanvasGradient | null = null
  let glowGrad: CanvasGradient | null = null

  function buildGradients(): void {
    if (!ctx) return
    dotGrad = ctx.createRadialGradient(0, 0, 0.25, 0, 0, 1)
    dotGrad.addColorStop(0, 'rgba(0, 0, 0, 0.85)')
    dotGrad.addColorStop(0.55, 'rgba(0, 0, 0, 0.76)')
    dotGrad.addColorStop(1, 'rgba(0, 0, 0, 0)')

    glowGrad = ctx.createRadialGradient(0, 0, 0, 0, 0, 1)
    glowGrad.addColorStop(0, `rgba(${CY}, 0.5)`)
    glowGrad.addColorStop(0.45, `rgba(${CY}, 0.15)`)
    glowGrad.addColorStop(1, `rgba(${CY}, 0)`)
  }

  /** 单位空间（半径 1）里的轮廓，靠 `ctx.scale(r, r)` 缩放，与半径无关。 */
  function stampPath(stamp: Stamp): void {
    if (!ctx) return
    ctx.beginPath()
    for (let i = 0; i <= SEGS; i++) {
      const a = (i / SEGS) * Math.PI * 2
      const rr = stamp.verts[i]
      const px = Math.cos(a) * rr
      const py = Math.sin(a) * rr
      if (i === 0) ctx.moveTo(px, py)
      else ctx.lineTo(px, py)
    }
    ctx.closePath()
  }

  function makeVerts(seed: number): number[] {
    const v: number[] = []
    for (let i = 0; i <= SEGS; i++) {
      const a = (i / SEGS) * Math.PI * 2
      v.push(
        0.78 +
          0.14 * Math.sin(a * 3 + seed) +
          0.08 * Math.sin(a * 7 + seed * 2.1) +
          0.05 * Math.sin(a * 13 + seed * 0.7)
      )
    }
    return v
  }

  function pushStamp(x: number, y: number, born: number): void {
    // 到顶就丢弃新点，**不要淘汰旧点**：淘汰会让快速划动时一段擦痕毫无过渡地整块消失
    if (stamps.length >= MAX_STAMPS) return
    stamps.push({ x, y, born, rmax: R_END * (0.55 + rand() * 0.45), verts: makeVerts(rand() * 6.28) })
  }

  function draw(now: number): void {
    if (!ctx || !dotGrad || !glowGrad) return

    if (stamps.length === 0 && veilFilled) return
    // 1) 每帧重铺整片遮罩 —— 这就是「愈合」
    ctx.globalCompositeOperation = 'source-over'
    ctx.globalAlpha = 1
    ctx.fillStyle = `rgba(${VEIL_RGB}, ${VEIL})`
    ctx.fillRect(0, 0, width, canvas.height / dpr)
    veilFilled = true
    if (stamps.length === 0) return

    // 2) 淘汰过期墨点
    stamps = stamps.filter((s) => now - s.born < LIFETIME)
    if (stamps.length === 0) return

    // 3) 擦开遮罩。单次最深只擦到 85%，留一层残余 → 读作「洇开」而不是「挖穿」
    ctx.globalCompositeOperation = 'destination-out'
    for (const s of stamps) {
      const t = (now - s.born) / LIFETIME
      const r = R_START + (s.rmax - R_START) * (1 - Math.pow(1 - t, 3)) // 先快后慢地扩张
      ctx.save()
      ctx.globalAlpha = Math.pow(1 - t, 1.6)
      ctx.translate(s.x, s.y)
      ctx.scale(r, r)
      ctx.fillStyle = dotGrad
      stampPath(s)
      ctx.fill()
      ctx.restore()
    }

    // 4) 在擦过的地方留下光。**深色主题必需**：遮罩只会减光，暗底上单靠擦除的揭示几乎看不见
    ctx.globalCompositeOperation = 'lighter'
    for (const s of stamps) {
      const t = (now - s.born) / LIFETIME
      const r = R_START + (s.rmax - R_START) * (1 - Math.pow(1 - t, 3))
      ctx.save()
      ctx.globalAlpha = Math.pow(1 - t, 1.6) * 0.3 // 0.2~0.35，过高会过曝成白
      ctx.translate(s.x, s.y)
      ctx.scale(r * 1.5, r * 1.5) // 光晕比洞略大
      ctx.fillStyle = glowGrad
      stampPath(s)
      ctx.fill()
      ctx.restore()
    }

    ctx.globalAlpha = 1
    ctx.globalCompositeOperation = 'source-over'
  }

  function frame(): void {
    draw(performance.now())
    if (stamps.length === 0) {
      running = false
      raf = 0
      return
    }
    raf = requestAnimationFrame(frame)
  }

  function start(): void {
    if (running) return
    running = true
    raf = requestAnimationFrame(frame)
  }

  function resize(): void {
    if (!ctx) return
    const w = canvas.clientWidth
    const h = canvas.clientHeight
    if (w <= 0 || h <= 0) return
    dpr = Math.min(window.devicePixelRatio || 1, 2)
    width = w
    // **重设 width 会清空画布** —— 遮罩是每帧重铺的，这里只需要把状态标回「没铺过」
    canvas.width = Math.round(w * dpr)
    canvas.height = Math.round(h * dpr)
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    veilFilled = false
    stamps = []
    lastX = null
    lastY = null
    buildGradients()
    draw(performance.now())
  }

  function move(x: number, y: number): void {
    if (width <= 0) return
    const now = performance.now()
    if (lastX === null || lastY === null) {
      pushStamp(x, y, now)
    } else {
      const dx = x - lastX
      const dy = y - lastY
      const dist = Math.sqrt(dx * dx + dy * dy)
      if (dist < 0.5) return
      const nx = -dy / dist
      const ny = dx / dist
      const steps = Math.max(1, Math.ceil(dist / STAMP_STEP))
      for (let i = 1; i <= steps; i++) {
        const u = i / steps
        // 法线抖动：不抖的话擦痕是一根均匀的管子，抖了才像「手抹」
        const jit = (rand() - 0.5) * 0.45 * R_END
        // 时间戳回拨：一次 pointermove 可能跨上百像素，整段共享一个 born 会整段同时愈合
        pushStamp(lastX + dx * u + nx * jit, lastY + dy * u + ny * jit, now - (steps - i) * 16)
      }
    }
    lastX = x
    lastY = y
    start()
  }

  function enter(): void {
    lastX = null
    lastY = null
  }

  function stop(): void {
    running = false
    if (raf) cancelAnimationFrame(raf)
    raf = 0
  }

  return { resize, move, enter, stop }
}

/* ============================================================================
   流星场：给静态底画叠一层会动的流星（登录页的用法）。
   ========================================================================== */

/** 生成间隔（ms）/ 速度（px/s）/ 尾长（相对屏宽）/ 寿命（ms）——四个区间。
    间隔要明显小于寿命，屏幕上才**同时**挂着几颗：一颗一颗地来不叫流星雨。 */
const SPAWN_GAP: [number, number] = [260, 900]
const METEOR_SPEED: [number, number] = [520, 940]
const METEOR_TRAIL: [number, number] = [0.12, 0.28]
const METEOR_LIFE: [number, number] = [1500, 2600]

interface Meteor {
  /** 头的位置与速度（px、px/s）。头是亮的那个点，尾迹由头往回推。 */
  x: number
  y: number
  vx: number
  vy: number
  trail: number
  born: number
  life: number
  thick: number
}

export interface MeteorField {
  resize(): void
  start(): void
  stop(): void
}

/**
 * 逐帧画流星。**必须画在单独一层透明画布上**：底画重绘一次要画上千颗星与几团星云，
 * 拿它逐帧重画等于把整页拖垮。
 *
 * 与底画同一套纪律：深底亮笔一律 `lighter` 加色（`source-over` 叠不出光）、
 * 尾迹宽度沿程收细（等宽的尾巴一眼假）、随机走固定种子
 * （`Math.random()` 逐帧取会让同一颗流星每帧换一个形状，看起来是在抖而不是在飞）。
 */
export function createMeteorField(
  canvas: HTMLCanvasElement,
  options: { seed?: number } = {}
): MeteorField {
  const ctx = canvas.getContext('2d')
  const rand = seeded(options.seed ?? 90210)
  let width = 0
  let height = 0
  let dpr = 1
  let raf = 0
  let running = false
  let meteors: Meteor[] = []
  let nextSpawnAt = 0
  /** 单位半径的光晕渐变：**只建一次**，靠 translate/scale 复用 */
  let headGrad: CanvasGradient | null = null

  const between = ([lo, hi]: [number, number]): number => lo + rand() * (hi - lo)

  function buildGradients(): void {
    if (!ctx) return
    headGrad = ctx.createRadialGradient(0, 0, 0, 0, 0, 1)
    headGrad.addColorStop(0, `rgba(${GLOW}, 0.95)`)
    headGrad.addColorStop(0.35, `rgba(${CY}, 0.42)`)
    headGrad.addColorStop(1, `rgba(${CY}, 0)`)
  }

  function spawn(now: number): Meteor {
    const speed = between(METEOR_SPEED) * (width < 720 ? 0.7 : 1)
    // 左下走向：与底画里那些静态流星同一个方向——两股风会让天空看起来是乱的
    const angle = 0.35 + rand() * 0.35
    return {
      x: width * (0.3 + rand() * 0.8),
      y: height * (-0.1 + rand() * 0.5),
      vx: -Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      trail: width * between(METEOR_TRAIL),
      born: now,
      life: between(METEOR_LIFE),
      thick: 1.6 + rand() * 1.1
    }
  }

  function drawMeteor(m: Meteor, now: number): void {
    if (!ctx) return
    const t = (now - m.born) / m.life
    // 淡入快、淡出慢：流星是「燃尽」的，不是走到某处被裁掉
    const alpha = Math.min(1, t / 0.16) * Math.min(1, (1 - t) / 0.42)
    if (alpha <= 0) return
    const age = (now - m.born) / 1000
    const headX = m.x + m.vx * age
    const headY = m.y + m.vy * age
    const len = Math.hypot(m.vx, m.vy) || 1
    // **运动方向**的单位向量。尾迹画在头的后面（head - 方向 × 长度）——正负写反的话
    // 拖尾会甩在头的前面，看起来是倒着飞的（改版时绊过一次）
    const ux = m.vx / len
    const uy = m.vy / len

    // 尾迹：一批从尾到头的点，宽度沿程收细（0 = 尾、1 = 头）
    const pts: [number, number][] = []
    const steps = 12
    for (let s = 0; s <= steps; s++) {
      const u = s / steps
      pts.push([headX - ux * m.trail * (1 - u), headY - uy * m.trail * (1 - u)])
    }
    ctx.globalAlpha = alpha * 0.75
    ribbon(ctx, pts, (u) => m.thick * Math.pow(u, 1.6) * 0.5, `rgba(${GLOW}, 0.55)`)

    // 头：一个小亮点 + 一圈比它大得多的光晕（「亮」是光晕给的，不是那个点）
    if (headGrad !== null) {
      ctx.globalAlpha = alpha
      ctx.save()
      ctx.translate(headX, headY)
      ctx.scale(m.thick * 7, m.thick * 7)
      ctx.fillStyle = headGrad
      ctx.beginPath()
      ctx.arc(0, 0, 1, 0, Math.PI * 2)
      ctx.fill()
      ctx.restore()
    }
    ctx.globalAlpha = 1
  }

  function draw(now: number): void {
    if (!ctx) return
    ctx.clearRect(0, 0, width, height)
    if (now >= nextSpawnAt) {
      meteors.push(spawn(now))
      nextSpawnAt = now + between(SPAWN_GAP)
    }
    meteors = meteors.filter((m) => now - m.born < m.life)
    for (const m of meteors) drawMeteor(m, now)
  }

  function frame(now: number): void {
    if (!running) return
    draw(now)
    raf = requestAnimationFrame(frame)
  }

  function start(): void {
    if (running || !ctx) return
    running = true
    // 头一颗稍等一下：与面板的入场动画错开，不然它一出现就被入场盖住
    nextSpawnAt = performance.now() + 900
    raf = requestAnimationFrame(frame)
  }

  function stop(): void {
    running = false
    if (raf) cancelAnimationFrame(raf)
    raf = 0
  }

  function resize(): void {
    if (!ctx) return
    const w = canvas.clientWidth
    const h = canvas.clientHeight
    if (w <= 0 || h <= 0) return
    dpr = Math.min(window.devicePixelRatio || 1, 2)
    width = w
    height = h
    canvas.width = Math.round(w * dpr)
    canvas.height = Math.round(h * dpr)
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    // 深底亮笔：整个流星层一律加色
    ctx.globalCompositeOperation = 'lighter'
    buildGradients()
  }

  return { resize, start, stop }
}
