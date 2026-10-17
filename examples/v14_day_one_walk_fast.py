"""Compatibility entry point for the maintained bounded PPO integration example."""

if __package__ in (None, ""):
    from v14_day_one_walk import main
else:
    from examples.v14_day_one_walk import main


if __name__ == "__main__":
    raise SystemExit(main())
