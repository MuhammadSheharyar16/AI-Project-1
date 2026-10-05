import { useEffect, useRef } from 'react'
import * as THREE from 'three'

const CYAN = 0x22e4ff
const LILAC = 0x9f85ff
const PINK = 0xff5fd2
const GREEN = 0x4dffb4
const RED = 0xff6b88

interface Packet {
  mesh: THREE.Mesh
  glow: THREE.SpriteMaterial
  trail: THREE.Sprite[]
  hit: boolean // already reached the shield on this journey
  fresh: boolean // just (re)started: its trail must snap to it
  ok: boolean
  t: number // 0 → 1 along its journey
  speed: number
  y: number
  z: number
}

/**
 * The firewall as a 3D object: answer "packets" fly in from the left, hit the shield core, and
 * either pass through (green) or are thrown back and fade (red).
 */
export function HeroScene() {
  const mountRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    mount.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100)
    camera.position.set(0, 0, 9)

    const shield = new THREE.Group()
    scene.add(shield)

    const additive = { transparent: true, blending: THREE.AdditiveBlending, depthWrite: false }

    // One soft radial texture, reused for every glow in the scene
    const glowCanvas = document.createElement('canvas')
    glowCanvas.width = glowCanvas.height = 128
    const context = glowCanvas.getContext('2d')!
    const gradient = context.createRadialGradient(64, 64, 0, 64, 64, 64)
    gradient.addColorStop(0, 'rgba(255, 255, 255, 1)')
    gradient.addColorStop(0.25, 'rgba(255, 255, 255, 0.45)')
    gradient.addColorStop(1, 'rgba(255, 255, 255, 0)')
    context.fillStyle = gradient
    context.fillRect(0, 0, 128, 128)
    const glowTexture = new THREE.CanvasTexture(glowCanvas)
    const makeGlow = (color: number, size: number, opacity: number) => {
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTexture, color, opacity, ...additive }))
      sprite.scale.setScalar(size)
      return sprite
    }

    // Halo behind the core: a wide lilac bloom with a tighter cyan heart
    const halo = makeGlow(0x7a5cff, 10, 0.6)
    halo.position.z = -1.5
    scene.add(halo)
    const heart = makeGlow(0x4fd8ff, 5, 0.6)
    heart.position.z = -0.5
    scene.add(heart)

    // Faceted core
    const coreGeometry = new THREE.IcosahedronGeometry(1.25, 0)
    const corePositions = coreGeometry.getAttribute('position')
    const coreColors = new Float32Array(corePositions.count * 3)
    const top = new THREE.Color(0x35f0ff)
    const middle = new THREE.Color(0x6a4dff)
    const base = new THREE.Color(0xff4fcf)
    const shade = new THREE.Color()
    for (let i = 0; i < corePositions.count; i++) {
      const height = corePositions.getY(i) / 1.25 // -1 (base) to 1 (top)
      if (height >= 0) shade.lerpColors(middle, top, height)
      else shade.lerpColors(middle, base, -height)
      shade.toArray(coreColors, i * 3)
    }
    coreGeometry.setAttribute('color', new THREE.BufferAttribute(coreColors, 3))
    const core = new THREE.Mesh(
      coreGeometry,
      new THREE.MeshStandardMaterial({
        vertexColors: true,
        emissive: 0x3b2bb5,
        emissiveIntensity: 0.35,
        metalness: 0.25,
        roughness: 0.22,
        flatShading: true,
      }),
    )
    shield.add(core)

    // Sharp glowing edges: an inner cage on the core and a larger outer cage
    const innerEdges = new THREE.LineSegments(
      new THREE.EdgesGeometry(coreGeometry),
      new THREE.LineBasicMaterial({ color: 0xffffff, opacity: 0.75, ...additive }),
    )
    innerEdges.scale.setScalar(1.01)
    shield.add(innerEdges)

    // A faint glass shell so the crystal looks cut and polished
    const shell = new THREE.Mesh(coreGeometry, new THREE.MeshBasicMaterial({ color: 0xffffff, opacity: 0.08, ...additive }))
    shell.scale.setScalar(1.16)
    shield.add(shell)

    const cageGeometry = new THREE.IcosahedronGeometry(2.05, 1)
    const cage = new THREE.LineSegments(
      new THREE.EdgesGeometry(cageGeometry),
      new THREE.LineBasicMaterial({ color: LILAC, opacity: 0.1, ...additive }),
    )
    scene.add(cage)

    // Round nodes (a point without a round texture renders as a square)
    const dotCanvas = document.createElement('canvas')
    dotCanvas.width = dotCanvas.height = 64
    const dotContext = dotCanvas.getContext('2d')!
    const dotGradient = dotContext.createRadialGradient(32, 32, 0, 32, 32, 32)
    dotGradient.addColorStop(0, 'rgba(255, 255, 255, 1)')
    dotGradient.addColorStop(0.45, 'rgba(255, 255, 255, 1)')
    dotGradient.addColorStop(1, 'rgba(255, 255, 255, 0)')
    dotContext.fillStyle = dotGradient
    dotContext.beginPath()
    dotContext.arc(32, 32, 32, 0, Math.PI * 2)
    dotContext.fill()
    const dotTexture = new THREE.CanvasTexture(dotCanvas)
    const cageDots = new THREE.Points(
      cageGeometry,
      new THREE.PointsMaterial({ color: 0xcfe9ff, size: 0.1, map: dotTexture, opacity: 0.9, ...additive }),
    )
    cage.add(cageDots)

    // The firewall itself: an energy shield that glows at its rim, with bands of light sweeping up it.
    // It flashes green or red whenever a packet reaches it.
    const shieldUniforms = {
      uTime: { value: 0 },
      uFlash: { value: 0 },
      uFlashColor: { value: new THREE.Color(GREEN) },
    }
    const bubble = new THREE.Mesh(
      new THREE.SphereGeometry(2.05, 64, 48),
      new THREE.ShaderMaterial({
        uniforms: shieldUniforms,
        vertexShader: `
          varying vec3 vNormal;
          varying vec3 vView;
          varying vec3 vPosition;
          void main() {
            vec4 viewPosition = modelViewMatrix * vec4(position, 1.0);
            vNormal = normalize(normalMatrix * normal);
            vView = normalize(-viewPosition.xyz);
            vPosition = position;
            gl_Position = projectionMatrix * viewPosition;
          }
        `,
        fragmentShader: `
          uniform float uTime;
          uniform float uFlash;
          uniform vec3 uFlashColor;
          varying vec3 vNormal;
          varying vec3 vView;
          varying vec3 vPosition;
          void main() {
            float rim = pow(1.0 - abs(dot(vNormal, vView)), 2.4);
            float height = vPosition.y / 2.05 * 0.5 + 0.5;
            vec3 base = mix(vec3(1.0, 0.37, 0.82), vec3(0.13, 0.89, 1.0), height);
            float bands = 0.5 + 0.5 * sin(vPosition.y * 10.0 - uTime * 1.8);
            float alpha = rim * (0.7 + 0.3 * bands) + 0.025;
            vec3 color = mix(base, uFlashColor, min(1.0, uFlash) * 0.55);
            gl_FragColor = vec4(color, alpha * (1.0 + uFlash * 0.7));
          }
        `,
        ...additive,
      }),
    )
    scene.add(bubble)

    // Burst of light where a packet meets the shield
    const spark = makeGlow(GREEN, 1, 0)
    scene.add(spark)
    let flash = 0

    // Orbit rings
    const rings: THREE.Mesh[] = []
    for (const [radius, tiltX, tiltY, color] of [
      [2.75, 1.25, 0.2, CYAN],
      [3.15, 1.75, -0.5, LILAC],
      [3.6, 1.45, 0.9, PINK],
    ] as const) {
      const ring = new THREE.Mesh(
        new THREE.TorusGeometry(radius, 0.016, 8, 200),
        new THREE.MeshBasicMaterial({ color, opacity: 0.75, ...additive }),
      )
      ring.rotation.set(tiltX, tiltY, 0)
      // A comet riding the ring: it orbits because the ring spins about its own axis
      const comet = makeGlow(color, 0.7, 1)
      comet.position.x = radius
      comet.add(makeGlow(0xffffff, 0.35, 1))
      ring.add(comet)
      scene.add(ring)
      rings.push(ring)
    }

    // Shield pulses: rings of light that expand from the core and fade
    const pulseGeometry = new THREE.RingGeometry(0.985, 1, 96)
    const pulses = [0, 1, 2].map((i) => {
      const pulse = new THREE.Mesh(
        pulseGeometry,
        new THREE.MeshBasicMaterial({ color: [CYAN, LILAC, PINK][i], side: THREE.DoubleSide, ...additive }),
      )
      scene.add(pulse)
      return pulse
    })

    // Star dust
    const dustCount = 700
    const dustPositions = new Float32Array(dustCount * 3)
    for (let i = 0; i < dustCount; i++) {
      const radius = 5 + Math.random() * 9
      const theta = Math.random() * Math.PI * 2
      const phi = Math.acos(2 * Math.random() - 1)
      dustPositions[i * 3] = radius * Math.sin(phi) * Math.cos(theta)
      dustPositions[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta) * 0.6
      dustPositions[i * 3 + 2] = radius * Math.cos(phi) - 4
    }
    const dustColors = new Float32Array(dustCount * 3)
    const palette = [CYAN, LILAC, PINK, 0xffffff].map((hex) => new THREE.Color(hex))
    for (let i = 0; i < dustCount; i++) {
      palette[Math.floor(Math.random() * palette.length)].toArray(dustColors, i * 3)
    }
    const dustGeometry = new THREE.BufferGeometry()
    dustGeometry.setAttribute('position', new THREE.BufferAttribute(dustPositions, 3))
    dustGeometry.setAttribute('color', new THREE.BufferAttribute(dustColors, 3))
    const dust = new THREE.Points(
      dustGeometry,
      new THREE.PointsMaterial({ size: 0.11, map: glowTexture, vertexColors: true, opacity: 0.9, ...additive }),
    )
    scene.add(dust)

    const START_X = -7
    const HIT_X = -2.05 // the shield's surface
    const END_X = 7
    const HIT_T = 0.5

    // Answer packets
    const packetGeometry = new THREE.SphereGeometry(0.06, 14, 14)
    const TRAIL = 6
    const PACKETS = 9
    const packets: Packet[] = []
    const resetPacket = (packet: Packet, t: number) => {
      packet.ok = Math.random() < 0.55
      packet.t = t
      packet.speed = 0.16 + Math.random() * 0.12
      packet.y = (Math.random() - 0.5) * 2.2
      packet.z = (Math.random() - 0.5) * 1.6
      packet.hit = t >= HIT_T
      packet.fresh = true
      ;(packet.mesh.material as THREE.MeshBasicMaterial).color.setHex(0xdff6ff)
      packet.glow.color.setHex(0xdff6ff)
    }
    for (let i = 0; i < PACKETS; i++) {
      const mesh = new THREE.Mesh(packetGeometry, new THREE.MeshBasicMaterial({ ...additive }))
      const glow = makeGlow(0xdff6ff, 0.6, 0.9)
      mesh.add(glow)
      const trail = Array.from({ length: TRAIL }, (_, j) => {
        const sprite = makeGlow(0xdff6ff, 0.4 - j * 0.05, 0)
        scene.add(sprite)
        return sprite
      })
      const packet: Packet = {
        mesh, glow: glow.material, trail, hit: false, fresh: true, ok: true, t: 0, speed: 0.2, y: 0, z: 0,
      }
      resetPacket(packet, i / PACKETS)
      scene.add(mesh)
      packets.push(packet)
    }

    scene.add(new THREE.AmbientLight(0xffffff, 0.9))
    const keyLight = new THREE.PointLight(0xffffff, 110, 30)
    keyLight.position.set(4, 3, 5)
    scene.add(keyLight)
    const rimLight = new THREE.PointLight(PINK, 90, 30)
    rimLight.position.set(-5, -2.5, 3)
    scene.add(rimLight)
    const topLight = new THREE.PointLight(CYAN, 70, 30)
    topLight.position.set(-1, 5, 4)
    scene.add(topLight)

    const pointer = { x: 0, y: 0 }
    const onPointerMove = (event: PointerEvent) => {
      pointer.x = (event.clientX / window.innerWidth) * 2 - 1
      pointer.y = (event.clientY / window.innerHeight) * 2 - 1
    }
    window.addEventListener('pointermove', onPointerMove)

    const resize = () => {
      const { clientWidth: width, clientHeight: height } = mount
      if (!width || !height) return
      renderer.setSize(width, height)
      camera.aspect = width / height
      // Pull back far enough that the outer rings fit inside the canvas at any size
      camera.position.z = width < 520 ? 11.5 : 9.6
      scene.position.y = 0
      camera.updateProjectionMatrix()
      // Resizing clears the canvas; redraw now so a paused (reduced-motion) scene is never left blank
      renderer.render(scene, camera)
    }
    const observer = new ResizeObserver(resize)
    observer.observe(mount)
    resize()


    const timer = new THREE.Timer()
    let frame = 0
    const render = () => {
      timer.update()
      const delta = Math.min(timer.getDelta(), 0.05)
      const elapsed = timer.getElapsed()

      shield.rotation.y += delta * 0.35
      shield.rotation.x = Math.sin(elapsed * 0.4) * 0.25
      cage.rotation.y -= delta * 0.12
      cage.rotation.z += delta * 0.05
      rings.forEach((ring, i) => (ring.rotation.z += delta * (0.25 - i * 0.14)))
      dust.rotation.y += delta * 0.01
      pulses.forEach((pulse, i) => {
        const phase = (elapsed * 0.28 + i / pulses.length) % 1
        pulse.scale.setScalar(1.5 + phase * 1.9)
        ;(pulse.material as THREE.MeshBasicMaterial).opacity = Math.sin(phase * Math.PI) * 0.2
      })
      ;(core.material as THREE.MeshStandardMaterial).emissiveIntensity = 0.35 + Math.sin(elapsed * 2) * 0.1
      heart.material.opacity = 0.5 + Math.sin(elapsed * 2) * 0.12
      flash *= Math.exp(-delta * 6)
      shieldUniforms.uTime.value = elapsed
      shieldUniforms.uFlash.value = flash
      spark.material.opacity = flash
      spark.scale.setScalar(0.6 + (1 - flash) * 1.8)

      for (const packet of packets) {
        packet.t += delta * packet.speed
        if (packet.t >= 1) resetPacket(packet, 0)
        const material = packet.mesh.material as THREE.MeshBasicMaterial
        const { t } = packet
        let x: number
        let y = packet.y
        material.opacity = Math.min(1, t * 8)
        if (t < HIT_T) {
          // Approach, converging on the core
          const k = t / HIT_T
          x = START_X + (HIT_X - START_X) * k
          y = packet.y * (1 - k * 0.75)
        } else {
          const k = (t - HIT_T) / (1 - HIT_T)
          const verdict = packet.ok ? GREEN : RED
          material.color.setHex(verdict)
          packet.glow.color.setHex(verdict)
          if (!packet.hit) {
            packet.hit = true
            flash = 1
            shieldUniforms.uFlashColor.value.setHex(verdict)
            spark.material.color.setHex(verdict)
            spark.position.set(HIT_X, packet.y * 0.25, packet.z * 0.2)
          }
          if (packet.ok) {
            // Passes through and continues to the customer
            x = HIT_X + (END_X - HIT_X) * k
            y = packet.y * 0.25
            material.opacity = k > 0.85 ? (1 - k) / 0.15 : 1
          } else {
            // Thrown back and dissolved
            x = HIT_X - k * 2.2
            y = packet.y * 0.25 + (packet.y >= 0 ? 1 : -1) * k * 2.4
            material.opacity = Math.max(0, 1 - k * 1.6)
          }
        }
        packet.glow.opacity = material.opacity * 0.9
        packet.mesh.position.set(x, y, packet.z * (1 - Math.min(1, t / HIT_T) * 0.8))
        // Tail: each sprite chases the one ahead of it
        let lead = packet.mesh.position
        packet.trail.forEach((sprite, j) => {
          if (packet.fresh) sprite.position.copy(lead)
          else sprite.position.lerp(lead, 0.4)
          sprite.material.color.copy(material.color)
          sprite.material.opacity = material.opacity * (0.55 - j * 0.085)
          lead = sprite.position
        })
        packet.fresh = false
      }

      // Pointer parallax
      scene.rotation.y += (pointer.x * 0.25 - scene.rotation.y) * 0.04
      scene.rotation.x += (pointer.y * 0.15 - scene.rotation.x) * 0.04

      renderer.render(scene, camera)
      if (!reducedMotion) frame = requestAnimationFrame(render)
    }
    render()

    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      window.removeEventListener('pointermove', onPointerMove)
      scene.traverse((object) => {
        if (object instanceof THREE.Mesh || object instanceof THREE.LineSegments || object instanceof THREE.Points) {
          object.geometry.dispose()
          ;(object.material as THREE.Material).dispose()
        } else if (object instanceof THREE.Sprite) {
          object.material.dispose()
        }
      })
      glowTexture.dispose()
      dotTexture.dispose()
      renderer.dispose()
      mount.removeChild(renderer.domElement)
    }
  }, [])

  return (
    <div className="hero-scene" aria-hidden="true">
      {/* The canvas stops above the legend bar, so the legend never covers the picture */}
      <div ref={mountRef} className="scene-canvas" />
      <span className="scene-tag in">AI answers in</span>
      <span className="scene-tag core">Firewall</span>
      <div className="scene-legend">
        <span className="draft">
          <i />
          <b>New AI answer</b>
          <em>not checked yet</em>
        </span>
        <span className="ok">
          <i />
          <b>Approved</b>
          <em>shown to the customer</em>
        </span>
        <span className="bad">
          <i />
          <b>Blocked</b>
          <em>safe message shown instead</em>
        </span>
      </div>
    </div>
  )
}
