import json
from pathlib import Path


class Json:

    """
    A class I made to interact with .json files
    """

    @staticmethod
    def get_path() -> str:
        """
        Gets the path to our `bot.py` file
        """
        return str(Path(__file__).parents[1])

    @staticmethod
    def read_json(filename) -> dict:
        """
        Reads and returns the data from a `.json` file
        """
        cwd = Json.get_path()
        with open(cwd + "/config/" + filename + ".json", "r") as f:
            data = json.load(f)
        return data

    @staticmethod
    def clear_json(filename) -> dict:
        """
        Clears out a `.json` file and returns its contents
        """
        data = Json.read_json(filename)

        cwd = Json.get_path()
        with open(cwd + "/config/" + filename + ".json", "w") as f:
            json.dump({}, f, indent=4)

        return data

    @staticmethod
    def write_json(data, filename) -> None:
        """
        Writes data to a `.json` file (prolly won't need since we already have a DB)
        """
        cwd = Json.get_path()
        og_data = Json.read_json(filename)
        og_data.update(data)
        with open(cwd + "/config/" + filename + ".json", "w") as f:
            json.dump(og_data, f, indent=4)
