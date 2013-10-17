"""
Simulates time itself to make the fake mode tests run even faster.
"""


pending_events = []
sleep_entrance_count = 0


def event_simulator_spawn_after(time_from_now_in_seconds, func, *args, **kw):
    """Fakes events without doing any actual waiting."""
    def __cb():
        func(*args, **kw)
    pending_events.append({"time": time_from_now_in_seconds, "func": __cb})


def event_simulator_spawn(func, *args, **kw):
    event_simulator_spawn_after(0, func, *args, **kw)


def event_simulator_sleep(time_to_sleep):
    """Simulates waiting for an event."""
    global sleep_entrance_count
    sleep_entrance_count += 1
    time_to_sleep = float(time_to_sleep)
    global pending_events
    run_once = False  # Ensure simulator runs even if the sleep time is zero.
    while not run_once or time_to_sleep > 0:
        run_once = True
        itr_sleep = 0.5
        for i in range(len(pending_events)):
            event = pending_events[i]
            event["time"] = event["time"] - itr_sleep
            if event["func"] is not None and event["time"] < 0:
                # Call event, but first delete it so this function can be
                # reentrant.
                func = event["func"]
                event["func"] = None
                try:
                    func()
                except Exception:
                    LOG.exception("Simulated event error.")
        time_to_sleep -= itr_sleep
    sleep_entrance_count -= 1
    if sleep_entrance_count < 1:
        # Clear out old events
        pending_events = [event for event in pending_events
                          if event["func"] is not None]


def monkey_patch():
    import time
    time.sleep = event_simulator_sleep
    import eventlet
    from eventlet import greenthread
    eventlet.sleep = event_simulator_sleep
    greenthread.sleep = event_simulator_sleep
    eventlet.spawn_after = event_simulator_spawn_after
    eventlet.spawn_n = event_simulator_spawn
    eventlet.spawn = NotImplementedError
