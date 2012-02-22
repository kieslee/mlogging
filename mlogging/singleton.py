import threading

class Singleton(object):
    _instance = None
    def __new__(class_, *args, **kwargs):
        if not isinstance(class_._instance, class_):
            class_._instance = object.__new__(class_, *args, **kwargs)
        return class_._instance

if __name__ == "__main__":
    s1 = Singleton()
    s2 = Singleton()
    s3 = Singleton()
    
    print s1, id(s1)    
    print s2, id(s2)
    print s3, id(s3)
