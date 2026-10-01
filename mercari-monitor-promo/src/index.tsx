import { registerRoot, Composition } from "remotion";
import { PromoVideo } from "./PromoVideo";

const FPS = 30;
const SCENE_DURATIONS = [119, 124, 122, 112, 102, 115];
const TRANS_FRAMES = 10;
const TOTAL_FRAMES =
  SCENE_DURATIONS.reduce((a, b) => a + b, 0) -
  TRANS_FRAMES * (SCENE_DURATIONS.length - 1);

const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="PromoVideo"
      component={PromoVideo}
      durationInFrames={TOTAL_FRAMES}
      fps={FPS}
      width={1080}
      height={1920}
    />
  );
};

registerRoot(RemotionRoot);