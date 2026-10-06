"""Explicit real-model qualification; run only after CI pinned resource setup."""


def test_real_local_planner_through_shared_dashboard():
    from scripts.accept_dashboard_local_planner import main

    main()
