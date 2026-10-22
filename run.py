#!/usr/bin/env python3
"""每日情报流水线入口。

用法:
  python run.py           # 正式运行（需要 OPENAI_API_KEY 环境变量）
  python run.py --mock    # 本地测试：真实抓取，但不调用 OpenAI
  python run.py --date 2026-10-22   # 指定日期（重跑会覆盖当天数据）
"""

import argparse

from src.pipeline import run


def main() -> None:
    parser = argparse.ArgumentParser(description="每日情报流水线")
    parser.add_argument("--mock", action="store_true", help="不调用 OpenAI，用占位数据测试全流程")
    parser.add_argument("--date", default=None, help="指定简报日期 YYYY-MM-DD，默认今天（北京时间）")
    args = parser.parse_args()
    run(mock=args.mock, date_override=args.date)


if __name__ == "__main__":
    main()
