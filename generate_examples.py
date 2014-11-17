import run_tests


def import_tests():
    from trove.tests.examples import snippets
    snippets.monkey_patch_uuid_and_date()


if __name__ == "__main__":
    run_tests.main(import_tests)
