import subprocess
import sys

LINES = [
    "你是不是也这样？煤炉好货刚上架就没了！",
    "手动刷新根本抢不过机器人，只能加价买。",
    "煤炉助手，9大平台0.3秒实时监控。",
    "Turbo全量Feed加速，速度提升100倍！",
    "一键代购代拍，订单全流程管理。",
    "GitHub开源免费，Star支持一下！",
]

VOICE = "zh-CN-YunxiNeural"
text = "。".join(LINES)

subprocess.run([
    "edge-tts",
    "--voice", VOICE,
    "--rate", "+10%",
    "--text", text,
    "--write-media", "public/voiceover.mp3",
    "--write-subtitles", "public/voiceover.srt",
], check=True)

print("配音生成完成: public/voiceover.mp3")
print("字幕生成完成: public/voiceover.srt")