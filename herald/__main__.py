""" Module __main__.py 

    

    Created on 23/09/2023
    By Jean-Marc Le Peuvédic
    © CalCool Studios SAS 2021-2023
"""
# Import system libraries
import sys

if sys.gettrace() is None:
    from gevent import monkey
    monkey.patch_all()

# Import public libraries

# Import application modules
from herald.herald import main

main()
