import numpy as np
from pytest import raises

from riptide import running_median


def running_median_naive(data, w):
    h = w // 2

    # The C++ running median implicitly pads both ends of the arrray with
    # the edge values, we reproduce this behaviour here
    padded_data = np.pad(data, (h, h), mode='edge')

    def med(imid):
        return np.median(padded_data[imid:imid+w])

    return np.asarray([med(i) for i in range(data.size)])


def test_rmed_exceptions():
    data = np.arange(10, dtype='float32')

    with raises(ValueError): # width must be odd
        running_median(data, 2)
    
    with raises(ValueError): # width must be < size
        running_median(data, data.size)

    with raises(ValueError): # data must be 1D
        running_median(np.zeros(shape=(4, 8)), 3)


def test_rmed():
    x = np.random.normal(size=100).astype('float32')
    widths = [1, 3, 5, 7, 11, 25, 37]

    for w in widths:
        assert np.array_equal(running_median(x, w), running_median_naive(x, w))


def test_rmed_non_contiguous_data():
    # Test added after realizing that passing non-memory-contiguous array slices
    # to running_median() returned incorrect results
    # Thanks to Akshay Suresh for finding and reporting the problem
    data = np.random.normal(size=300).reshape(100, 3).astype('float32')
    widths = [1, 3, 5, 7, 11, 25, 37]

    # Calculate running median of columns
    for x in data.T:
        for w in widths:
            assert np.array_equal(running_median(x, w), running_median_naive(x, w))
