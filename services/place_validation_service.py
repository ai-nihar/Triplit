from models.place import Place


def is_valid_place(place: Place) -> bool:
    return bool(place.name)
