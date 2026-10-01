import React from "react";
import {
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
  AbsoluteFill,
  Audio,
  staticFile,
} from "remotion";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { parseSrt } from "@remotion/captions";
import type { Caption } from "@remotion/captions";

const COLORS = {
  bg: "#0a0a1a",
  surface: "#12122a",
  card: "#1a1a3e",
  border: "#2a2a5e",
  pink: "#ff6b9d",
  magenta: "#c44dff",
  cyan: "#00e5ff",
  orange: "#ff9100",
  lime: "#76ff03",
  gold: "#ffd740",
  text: "#f0f0ff",
  gray: "#8888aa",
};

const SPRING = { mass: 0.6, damping: 14, stiffness: 180 };
const FPS = 30;
const TRANS_FRAMES = 10;
const SCENE_DURATIONS = [119, 124, 122, 112, 102, 115];

const GITHUB_URL = "github.com/lyp0746/mercari-monitor";

const SRT_TEXT = `1
00:00:00,100 --> 00:00:03,761
煤炉好货秒没

2
00:00:03,761 --> 00:00:07,568
手动刷新太慢了

3
00:00:07,568 --> 00:00:11,318
煤炉助手9平台监控

4
00:00:11,318 --> 00:00:14,761
速度提升100倍

5
00:00:14,761 --> 00:00:17,897
一键代购代拍

6
00:00:17,897 --> 00:00:21,443
GitHub开源免费`;

const PARSED_CAPTIONS = parseSrt({ input: SRT_TEXT }).captions;

const CaptionOverlay: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentMs = (frame / fps) * 1000;
  const active = PARSED_CAPTIONS.find(
    (c: Caption) => currentMs >= c.startMs && currentMs <= c.endMs
  );
  if (!active) return null;
  const progress =
    (currentMs - active.startMs) / (active.endMs - active.startMs);
  const chars = Math.ceil(active.text.length * Math.min(progress * 1.5, 1));

  return (
    <div
      style={{
        position: "absolute",
        bottom: 180,
        left: 0,
        right: 0,
        textAlign: "center",
        fontSize: 44,
        fontWeight: 700,
        color: "white",
        textShadow: "0 2px 12px rgba(0,0,0,0.9)",
        zIndex: 100,
      }}
    >
      <span style={{ color: "white" }}>{active.text.slice(0, chars)}</span>
      <span style={{ opacity: 0.3 }}>{active.text.slice(chars)}</span>
    </div>
  );
};

const ParticleField: React.FC<{ count: number; color?: string }> = ({ count, color }) => {
  const frame = useCurrentFrame();
  const c = color || COLORS.magenta;
  const particles = React.useMemo(() => {
    return Array.from({ length: count }, (_, i) => ({
      x: Math.random() * 1080,
      y: Math.random() * 1920,
      size: 1 + Math.random() * 2.5,
      speed: 0.3 + Math.random() * 0.8,
      phase: Math.random() * Math.PI * 2,
    }));
  }, [count]);

  return (
    <>
      {particles.map((p, i) => {
        const opacity = interpolate(
          Math.sin(frame * 0.03 + p.phase),
          [-1, 1],
          [0.15, 0.6]
        );
        const yOffset = (frame * p.speed) % 1920;
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: p.x,
              top: (p.y + yOffset) % 1920,
              width: p.size,
              height: p.size,
              borderRadius: "50%",
              background: c,
              opacity,
              boxShadow: `0 0 ${p.size * 3}px ${c}`,
            }}
          />
        );
      })}
    </>
  );
};

const PulseGlow: React.FC<{
  x: number;
  y: number;
  color: string;
  size: number;
}> = ({ x, y, color, size }) => {
  const frame = useCurrentFrame();
  const scale = interpolate(Math.sin(frame * 0.06), [-1, 1], [0.8, 1.2]);
  const opacity = interpolate(Math.sin(frame * 0.06), [-1, 1], [0.3, 0.7]);

  return (
    <div
      style={{
        position: "absolute",
        left: x - size / 2,
        top: y - size / 2,
        width: size,
        height: size,
        borderRadius: "50%",
        background: `radial-gradient(circle, ${color} 0%, transparent 70%)`,
        opacity,
        transform: `scale(${scale})`,
      }}
    />
  );
};

const SpringText: React.FC<{
  children: React.ReactNode;
  delay: number;
  style?: React.CSSProperties;
}> = ({ children, delay, style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const progress = spring({
    frame: Math.max(0, frame - delay),
    fps,
    config: SPRING,
  });
  const opacity = interpolate(progress, [0, 1], [0, 1]);
  const translateY = interpolate(progress, [0, 1], [40, 0]);

  return (
    <div
      style={{
        opacity,
        transform: `translateY(${translateY}px)`,
        ...style,
      }}
    >
      {children}
    </div>
  );
};

const Scene1: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const titleProgress = spring({ frame, fps, config: SPRING });
  const titleScale = interpolate(titleProgress, [0, 1], [0.5, 1]);
  const titleOpacity = interpolate(titleProgress, [0, 1], [0, 1]);

  return (
    <AbsoluteFill
      style={{ backgroundColor: COLORS.bg, justifyContent: "center", alignItems: "center" }}
    >
      <ParticleField count={40} color={COLORS.pink} />
      <PulseGlow x={540} y={800} color={COLORS.pink} size={300} />
      <div
        style={{
          opacity: titleOpacity,
          transform: `scale(${titleScale})`,
          textAlign: "center",
        }}
      >
        <div
          style={{
            fontSize: 96,
            fontWeight: 900,
            color: COLORS.pink,
            textShadow: `0 0 40px ${COLORS.pink}, 0 0 80px ${COLORS.pink}40`,
            lineHeight: 1.2,
            marginBottom: 20,
          }}
        >
          煤炉好货
        </div>
        <div
          style={{
            fontSize: 96,
            fontWeight: 900,
            color: COLORS.pink,
            textShadow: `0 0 40px ${COLORS.pink}, 0 0 80px ${COLORS.pink}40`,
            lineHeight: 1.2,
          }}
        >
          秒没！
        </div>
      </div>
      <SpringText delay={20} style={{ marginTop: 40, textAlign: "center" }}>
        <div style={{ fontSize: 36, color: COLORS.gray }}>
          你是不是也这样？
        </div>
      </SpringText>
    </AbsoluteFill>
  );
};

const Scene2: React.FC = () => {
  const steps = [
    { icon: "🔄", text: "手动刷新", color: COLORS.orange },
    { icon: "💨", text: "被抢空", color: COLORS.pink },
    { icon: "💰", text: "加价买", color: COLORS.pink },
  ];

  return (
    <AbsoluteFill
      style={{
        backgroundColor: COLORS.bg,
        justifyContent: "center",
        alignItems: "center",
        padding: 60,
      }}
    >
      <SpringText delay={5} style={{ textAlign: "center", marginBottom: 60 }}>
        <div style={{ fontSize: 52, fontWeight: 900, color: COLORS.text }}>
          手动刷新太慢了
        </div>
      </SpringText>
      {steps.map((step, i) => (
        <SpringText key={i} delay={15 + i * 15}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 20,
              padding: "24px 40px",
              marginBottom: 20,
              background: COLORS.card,
              borderRadius: 16,
              borderLeft: `4px solid ${step.color}`,
              width: 600,
            }}
          >
            <span style={{ fontSize: 40 }}>{step.icon}</span>
            <span
              style={{
                fontSize: 40,
                fontWeight: 700,
                color: step.color,
              }}
            >
              {step.text}
            </span>
          </div>
        </SpringText>
      ))}
    </AbsoluteFill>
  );
};

const Scene3: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const titleProgress = spring({ frame, fps, config: SPRING });
  const titleScale = interpolate(titleProgress, [0, 1], [0.6, 1]);

  const platforms = [
    "Mercari",
    "Yahoo!",
    "駿河屋",
    "楽天",
    "PayPay",
    "Fril",
    "Bunjang",
    "Carousell",
    "Yahoo!Shop",
  ];

  const numProgress = spring({
    frame: Math.max(0, frame - 15),
    fps,
    config: SPRING,
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: COLORS.bg,
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      <PulseGlow x={540} y={600} color={COLORS.magenta} size={400} />
      <div
        style={{
          opacity: interpolate(titleProgress, [0, 1], [0, 1]),
          transform: `scale(${titleScale})`,
          textAlign: "center",
          marginBottom: 40,
        }}
      >
        <div style={{ fontSize: 72, fontWeight: 900, color: COLORS.cyan }}>
          煤炉助手
        </div>
      </div>
      <SpringText delay={10}>
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "center",
            gap: 12,
          }}
        >
          <div
            style={{
              fontSize: 80,
              fontWeight: 900,
              color: COLORS.lime,
              transform: `scale(${interpolate(numProgress, [0, 1], [0.5, 1])})`,
            }}
          >
            9
          </div>
          <div style={{ fontSize: 44, fontWeight: 700, color: COLORS.text }}>
            平台
          </div>
          <div style={{ fontSize: 44, color: COLORS.gray }}>·</div>
          <div
            style={{
              fontSize: 80,
              fontWeight: 900,
              color: COLORS.lime,
              transform: `scale(${interpolate(numProgress, [0, 1], [0.5, 1])})`,
            }}
          >
            0.3
          </div>
          <div style={{ fontSize: 44, fontWeight: 700, color: COLORS.text }}>
            秒监控
          </div>
        </div>
      </SpringText>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: 12,
          marginTop: 40,
          padding: "0 120px",
        }}
      >
        {platforms.map((p, i) => (
          <SpringText key={i} delay={20 + i * 3}>
            <div
              style={{
                padding: "10px 16px",
                background: COLORS.card,
                borderRadius: 10,
                textAlign: "center",
                fontSize: 22,
                fontWeight: 600,
                color: COLORS.text,
                border: `1px solid ${COLORS.border}`,
              }}
            >
              {p}
            </div>
          </SpringText>
        ))}
      </div>
    </AbsoluteFill>
  );
};

const Scene4: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const beforeProgress = spring({
    frame: Math.max(0, frame - 5),
    fps,
    config: SPRING,
  });
  const afterProgress = spring({
    frame: Math.max(0, frame - 30),
    fps,
    config: SPRING,
  });

  const arrowProgress = spring({
    frame: Math.max(0, frame - 20),
    fps,
    config: SPRING,
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: COLORS.bg,
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      <SpringText delay={5} style={{ textAlign: "center", marginBottom: 60 }}>
        <div style={{ fontSize: 48, fontWeight: 900, color: COLORS.text }}>
          Turbo 全量 Feed 加速
        </div>
      </SpringText>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 40,
        }}
      >
        <div
          style={{
            opacity: interpolate(beforeProgress, [0, 1], [0, 1]),
            transform: `scale(${interpolate(beforeProgress, [0, 1], [0.8, 1])})`,
            textAlign: "center",
          }}
        >
          <div
            style={{
              fontSize: 72,
              fontWeight: 900,
              color: COLORS.pink,
              textShadow: `0 0 20px ${COLORS.pink}60`,
            }}
          >
            30s
          </div>
          <div style={{ fontSize: 28, color: COLORS.gray, marginTop: 8 }}>
            手动刷新
          </div>
        </div>
        <div
          style={{
            opacity: interpolate(arrowProgress, [0, 1], [0, 1]),
            transform: `translateX(${interpolate(arrowProgress, [0, 1], [-20, 0])}px)`,
          }}
        >
          <div style={{ fontSize: 60, color: COLORS.cyan }}>→</div>
        </div>
        <div
          style={{
            opacity: interpolate(afterProgress, [0, 1], [0, 1]),
            transform: `scale(${interpolate(afterProgress, [0, 1], [0.5, 1])})`,
            textAlign: "center",
          }}
        >
          <div
            style={{
              fontSize: 72,
              fontWeight: 900,
              color: COLORS.lime,
              textShadow: `0 0 30px ${COLORS.lime}60`,
            }}
          >
            0.3s
          </div>
          <div style={{ fontSize: 28, color: COLORS.gray, marginTop: 8 }}>
            Turbo模式
          </div>
        </div>
      </div>
      <SpringText delay={45} style={{ marginTop: 50, textAlign: "center" }}>
        <div
          style={{
            fontSize: 40,
            fontWeight: 700,
            color: COLORS.lime,
            textShadow: `0 0 15px ${COLORS.lime}40`,
          }}
        >
          速度提升 100 倍
        </div>
      </SpringText>
    </AbsoluteFill>
  );
};

const Scene5: React.FC = () => {
  const features = [
    { icon: "🔍", text: "实时监控", color: COLORS.cyan },
    { icon: "🛒", text: "一键代购", color: COLORS.lime },
    { icon: "🔨", text: "一键代拍", color: COLORS.orange },
    { icon: "📦", text: "订单管理", color: COLORS.magenta },
    { icon: "📱", text: "TG/DC推送", color: COLORS.pink },
    { icon: "💻", text: "Web+桌面", color: COLORS.cyan },
  ];

  return (
    <AbsoluteFill
      style={{
        backgroundColor: COLORS.bg,
        justifyContent: "center",
        alignItems: "center",
        padding: 60,
      }}
    >
      <SpringText delay={5} style={{ textAlign: "center", marginBottom: 50 }}>
        <div style={{ fontSize: 48, fontWeight: 900, color: COLORS.text }}>
          全流程覆盖
        </div>
      </SpringText>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(2, 1fr)",
          gap: 20,
          padding: "0 80px",
        }}
      >
        {features.map((f, i) => (
          <SpringText key={i} delay={12 + i * 8}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 16,
                padding: "20px 28px",
                background: COLORS.card,
                borderRadius: 14,
                borderLeft: `4px solid ${f.color}`,
              }}
            >
              <span style={{ fontSize: 36 }}>{f.icon}</span>
              <span
                style={{
                  fontSize: 32,
                  fontWeight: 700,
                  color: COLORS.text,
                }}
              >
                {f.text}
              </span>
            </div>
          </SpringText>
        ))}
      </div>
    </AbsoluteFill>
  );
};

const Scene6: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const titleProgress = spring({ frame, fps, config: SPRING });
  const pulseScale = interpolate(Math.sin(frame * 0.08), [-1, 1], [0.95, 1.05]);

  return (
    <AbsoluteFill
      style={{
        backgroundColor: COLORS.bg,
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      <ParticleField count={25} color={COLORS.magenta} />
      <div
        style={{
          opacity: interpolate(titleProgress, [0, 1], [0, 1]),
          transform: `scale(${interpolate(titleProgress, [0, 1], [0.6, 1])})`,
          textAlign: "center",
        }}
      >
        <div
          style={{
            fontSize: 64,
            fontWeight: 900,
            color: COLORS.cyan,
            marginBottom: 30,
          }}
        >
          煤炉助手
        </div>
      </div>
      <SpringText delay={10}>
        <div
          style={{
            padding: "20px 40px",
            background: COLORS.card,
            borderRadius: 14,
            border: `1px solid ${COLORS.border}`,
            textAlign: "center",
          }}
        >
          <div style={{ fontSize: 16, color: COLORS.gray, marginBottom: 8 }}>
            GitHub 开源免费
          </div>
          <div
            style={{
              fontSize: 28,
              fontFamily: "Consolas, monospace",
              fontWeight: 700,
              color: COLORS.text,
            }}
          >
            {GITHUB_URL}
          </div>
        </div>
      </SpringText>
      <SpringText delay={25}>
        <div
          style={{
            marginTop: 30,
            padding: "16px 48px",
            background: `linear-gradient(135deg, ${COLORS.pink}, ${COLORS.magenta})`,
            borderRadius: 30,
            transform: `scale(${pulseScale})`,
            textAlign: "center",
          }}
        >
          <span style={{ fontSize: 32, fontWeight: 900, color: "#fff" }}>
            ⭐ Star 支持一下
          </span>
        </div>
      </SpringText>
    </AbsoluteFill>
  );
};

const SRT_CAPTIONS = [
  { startMs: 100, endMs: 3761 },
  { startMs: 3761, endMs: 7568 },
  { startMs: 7568, endMs: 11318 },
  { startMs: 11318, endMs: 14761 },
  { startMs: 14761, endMs: 17897 },
  { startMs: 17897, endMs: 21443 },
];

const BgmWithDucking: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const bgmVolumeCallback = React.useCallback(
    (f: number) => {
      const currentMs = (f / fps) * 1000;
      const isSpeaking = SRT_CAPTIONS.some(
        (c) => currentMs >= c.startMs - 300 && currentMs <= c.endMs + 300
      );
      return isSpeaking ? 0.15 : 0.40;
    },
    [fps]
  );

  return <Audio src={staticFile("bgm.mp3")} volume={bgmVolumeCallback} />;
};

export const PromoVideo: React.FC = () => {
  return (
    <>
      <Audio src={staticFile("voiceover.mp3")} volume={() => 1.5} />
      <BgmWithDucking />
      <CaptionOverlay />
      <TransitionSeries>
        <TransitionSeries.Sequence durationInFrames={SCENE_DURATIONS[0]}>
          <Scene1 />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: TRANS_FRAMES })}
        />
        <TransitionSeries.Sequence durationInFrames={SCENE_DURATIONS[1]}>
          <Scene2 />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition
          presentation={slide()}
          timing={linearTiming({ durationInFrames: TRANS_FRAMES })}
        />
        <TransitionSeries.Sequence durationInFrames={SCENE_DURATIONS[2]}>
          <Scene3 />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: TRANS_FRAMES })}
        />
        <TransitionSeries.Sequence durationInFrames={SCENE_DURATIONS[3]}>
          <Scene4 />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition
          presentation={slide()}
          timing={linearTiming({ durationInFrames: TRANS_FRAMES })}
        />
        <TransitionSeries.Sequence durationInFrames={SCENE_DURATIONS[4]}>
          <Scene5 />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: TRANS_FRAMES })}
        />
        <TransitionSeries.Sequence durationInFrames={SCENE_DURATIONS[5]}>
          <Scene6 />
        </TransitionSeries.Sequence>
      </TransitionSeries>
    </>
  );
};