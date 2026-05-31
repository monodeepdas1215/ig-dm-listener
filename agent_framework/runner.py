import asyncio
import os
import sys

def main():
    runner_type = os.environ.get("RUNNER_TYPE", "cli").lower()

    if runner_type == "fastapi":
        from agent_framework.runners.fastapi_runner import FastAPIRunner
        runner = FastAPIRunner()
    elif runner_type == "cron":
        from agent_framework.runners.cron_runner import CronRunner
        runner = CronRunner()
    elif runner_type == "cli":
        from agent_framework.runners.cli_runner import CLIRunner
        runner = CLIRunner()
    else:
        print(f"Unknown RUNNER_TYPE: {runner_type}")
        sys.exit(1)

    try:
        asyncio.run(runner.start())
    except KeyboardInterrupt:
        print("Interrupted by user, shutting down.")
    except Exception as e:
        print(f"Runner failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
