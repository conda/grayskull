from abc import ABCMeta, abstractmethod


class AbstractStrategy(metaclass=ABCMeta):
    @staticmethod
    @abstractmethod
    def fetch_data(recipe, config, sections=None):
        ...
