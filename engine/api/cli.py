import argparse
from engine.core.config.container import Container


def main():
    parser = argparse.ArgumentParser("kaizen-engine")
    parser.add_argument("--run", help="Run a TestSpec by id")
    args = parser.parse_args()

    container = Container()
    # TODO: wire services and execute
    print("Engine CLI skeleton OK.", args)


if __name__ == "__main__":
    main()
