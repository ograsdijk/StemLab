import time
from timeit import default_timer
import logging
logger = logging.getLogger(__file__)
from collections import OrderedDict

def time():
    """ returns the time. used instead of time.time for rapid portability"""
    return default_timer()

def get_unique_name_list_from_class_list(cls_list):
    """
    returns a list of names using cls.name if unique or cls.name1, cls.name2... otherwise.
    Order of the name list matches order of cls_list, such that iterating over zip(cls_list, name_list) is OK
    """
    # cls_list is typically
    # cls_modules = [rp.HK, rp.AMS, rp.Scope, rp.Sampler, rp.Asg1, rp.Asg2] + \
    #              [rp.AuxOutput] * 2 + [rp.IQ] * 3 + [rp.Pid] * 4 + [rp.IIR]

    # first, map from list of classes to a list of corresponding names
    # e.g. all_names = ['hk, ..., 'pwm', 'pwm', ...
    all_names = [cls.__name__.lower() for cls in cls_list]
    final_names = []
    for name in all_names:
        # how many times does the name occur?
        occurences = all_names.count(name)
        if occurences == 1:
            # for single names, leave as-is
            final_names.append(name)
        else:
            # for multiple name, assign name+str(lowest_free_number)
            for i in range(occurences):
                if not name+str(i) in final_names:
                    final_names.append(name+str(i))
                    break
    return final_names


def recursive_getattr(root, path):
    """ returns root.path (i.e. root.attr1.attr2) """
    attribute = root
    for name in path.split('.'):
        if name != "":
            attribute = getattr(attribute, name)
    return attribute


def recursive_setattr(root, path, value):
    """ returns root.path = value (i.e. root.attr1.attr2 = value) """
    attribute = root
    names = path.split('.')
    for name in names[:-1]:
        attribute = getattr(attribute, name)
    setattr(attribute, names[-1], value)


def unique_list(nonunique_list):
    """ Returns a list where each element of nonunique_list occurs exactly once.
    The last occurence of an element defines its position in the returned list.
    """
    unique_list = []
    for attr in reversed(nonunique_list):
        # remove all previous occurences
        if attr not in unique_list:
            unique_list.insert(0, attr)
    return unique_list


class DuplicateFilter(logging.Filter):
    """
    Prevent multiple repeated logging message from polluting the console
    """
    def filter(self, record):
        # add other fields if you need more granular comparison, depends on your app
        current_log = (record.module, record.levelno, record.msg)
        if current_log != getattr(self, "last_log", None):
            self.last_log = current_log
            return True
        return False


def sorted_dict(dict_to_sort=None, sort_by_values=True, **kwargs):
    if dict_to_sort is None:
        dict_to_sort = kwargs
    if not sort_by_values:
        return OrderedDict(sorted(dict_to_sort.items()))
    else:
        return OrderedDict(sorted(dict_to_sort.items(), key=lambda x: x[1]))
