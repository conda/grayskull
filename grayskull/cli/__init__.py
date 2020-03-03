import progressbar

WIDGET_BAR_DOWNLOAD = [
    progressbar.Percentage(),
    " ",
    progressbar.ETA(format="%(eta)8s"),
    " ",
    progressbar.AdaptiveTransferSpeed(),
    progressbar.Bar(),
]


registry = {}


class RegisteringType(type):
    def __init__(cls, name, bases, attrs):
        for key, val in attrs.items():
            properties = getattr(val, "register", None)
            if properties is not None:
                registry["%s.%s" % (name, key)] = getattr(cls, key)


def register(*args):
    def decorator(f):
        f.register = tuple(args)
        return f

    return decorator


class MyClass(metaclass=RegisteringType):
    @register("prop1", "prop2")
    def my_method(self, arg2):
        pass

    @register("prop3", "prop4")
    def my_other_method(self, arg2):
        pass


print(registry)
