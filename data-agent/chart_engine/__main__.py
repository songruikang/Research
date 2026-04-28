"""python -m chart_engine 入口。"""
import sys

if len(sys.argv) > 1 and sys.argv[1] == "serve":
    from chart_engine.server import serve
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("serve")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--config", "-c")
    args = parser.parse_args()
    serve(host=args.host, port=args.port)

elif len(sys.argv) > 1 and sys.argv[1] == "examples":
    from chart_engine.cli.examples import ExampleManager
    from chart_engine.config import load_config
    import argparse

    parser = argparse.ArgumentParser(description="批量生成 few-shot 示例图表")
    parser.add_argument("examples")
    parser.add_argument("--input", "-i", help="few-shot JSON 文件路径（默认从 config 读取）")
    parser.add_argument("--output", "-o", default="chart_engine/examples_out/", help="输出目录")
    parser.add_argument("--config", "-c", help="配置文件路径")
    parser.add_argument("--base-dir", default=".", help="项目根目录")
    parser.add_argument("--mock", action="store_true", default=True, help="Mock 模式：不调 LLM（默认）")
    parser.add_argument("--llm", action="store_true", help="使用 LLM 生成（需要配置模型）")
    args = parser.parse_args()

    config = load_config(args.config)
    mgr = ExampleManager(config, base_dir=args.base_dir)
    use_mock = not args.llm
    results = mgr.generate_all(args.output, input_path=args.input, mock=use_mock)

    ok = sum(1 for r in results if r["status"] == "ok")
    mode = "Mock" if use_mock else "LLM"
    print(f"\n完成（{mode}模式）：{ok}/{len(results)} 个示例生成成功")
    print(f"HTML 预览: {args.output}/index.html")

else:
    from chart_engine.cli import main
    main()
