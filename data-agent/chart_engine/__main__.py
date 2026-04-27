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
    from chart_engine.examples import ExampleManager
    from chart_engine.config import load_config
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("examples")
    parser.add_argument("--output", "-o", default="chart_engine_examples/")
    parser.add_argument("--config", "-c")
    parser.add_argument("--base-dir", default=".")
    args = parser.parse_args()
    config = load_config(args.config)
    mgr = ExampleManager(config, base_dir=args.base_dir)
    results = mgr.generate_all(args.output)
    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"完成：{ok}/{len(results)} 个示例生成成功")
else:
    from chart_engine.cli import main
    main()
