"""
Web端启动入口
使用方法: uv run python run_web.py
或直接: uv run uvicorn src.api.main:app --reload
"""

import sys
import os
import uvicorn

def main():
    """启动Web API服务器"""
    
    print("""
╔════════════════════════════════════════╗
║     煤炉助手 - Web服务 v3.0           ║
║     多平台日淘代购监控系统              ║
╚════════════════════════════════════════╝
""")
    
    config = {
        "app": "src.api.main:app",
        "host": "0.0.0.0",
        "port": 8000,
        "reload": True,
        "workers": 1,
        "log_level": "info",
        "access_log": False,
    }
    
    print(f"🚀 启动Web服务...")
    print(f"   地址: http://{config['host']}:{config['port']}")
    print(f"   文档: http://{config['host']}:{config['port']}/docs")
    print(f"   模式: {'开发(热重载)' if config['reload'] else '生产'}")
    print()
    
    try:
        uvicorn.run(**config)
    except KeyboardInterrupt:
        print("\n\n✅ Web服务已停止")
    except Exception as e:
        print(f"\n❌ 启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()