import sys
import pytest

if __name__ == '__main__':
    ret = pytest.main(['-q'])
    print('\nPYTEST_RETURN_CODE=', ret)
    sys.exit(ret)
