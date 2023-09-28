# Import system libraries
import sys

if sys.gettrace() is None:
    from gevent import monkey
    monkey.patch_all()

# Import application modules
from herald.herald import main

main()
