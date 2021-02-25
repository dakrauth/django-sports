import random


def temporary_slug():
    return '{:10.0f}'.format(random.random() * 10000000000)
