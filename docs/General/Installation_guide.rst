Installation Guide
******************

Setting up the environment using Python3
++++++++++++++++++++++++++++++++++++++++

Step 1 : Make sure you have a Python3 version installed. Check your python version with the following command and update the python version, if necessary::

   python --version

Step 2: Clone the `OpenSCHC repository <https://github.com/openschc/openschc>`_ .

Step 3: For testing a simple example using SCHC under different scenarios, see `https://github.com/openschc/openschc/blob/master/src/README.rst <https://github.com/openschc/openschc/blob/master/src/README.md>`_.

Setting up the environment using micropython
++++++++++++++++++++++++++++++++++++++++++++

Micropython is Python3 for microcontrollers, but it also runs on Windows/Linux/Unix machine. Ues this to test your code on a computer before trying on an embedded device.

Step 1: install micropython. Some pointers are indicated below. For more details, please refer to the relevant documentation.

* Micropython GitHub project: (`https://github.com/micropython/micropython <https://github.com/micropython/micropython>`_ .
* For Linux distribs, specific instructions for the Unix port of micropython can be found at (it should be noted that this has not been tested on all Linux distribs): `https://github.com/micropython/micropython#the-unix-version <https://github.com/micropython/micropython#the-unix-version>`_
* On OSX

   * either recompile from the GitHub project, see `https://github.com/micropython/micropython/wiki/Micro-Python-on-Mac-OSX <https://github.com/micropython/micropython/wiki/Micro-Python-on-Mac-OSX>`_ .
   * or install with Brew: ``brew install micropython``
   * Note: on OS X, if you get an error message about missing libffi, try the fix described in `https://stackoverflow.com/questions/22875270/error-installing-bcrypt-with-pip-on-os-x-cant-find-ffi-h-libffi-is-installed/25854749#25854749 <https://stackoverflow.com/questions/22875270/error-installing-bcrypt-with-pip-on-os-x-cant-find-ffi-h-libffi-is-installed/25854749#25854749>`_

Step 2: download the needed micropython modules.

Modules to be installed in order to run SCHC are:

* argparse.py : ``./micropython -m upip install micropython-argparse``
* copy.py : ``./micropython -m upip install micropython-copy``
* types.py : ``./micropython -m upip install micropython-types``

Libs are located under ``~/.micropython/lib``

Step 3: Test the SCHC C/D and F/R

The following command line will simulate a simple ICMPv6 echo request/response using the SCHC protocol between the SCHC device and the gateway. The input JSON files are part of the SCHC orchestrator configuration (as you can see in the architecture figure above), and the loss parameters configure the link simulator to simulate packet drops on the radio link.

As you can see from the results of the below command, the 1st and the 2nd SCHC fragments are lost. Therefore, when the sender transmits the last fragment that includes the MIC, the receiver MIC check fails.
Consequently, the sender retransmits the 1st and 2nd fragments and when the receiver receives all the fragments with the MIC, the transmission is successful::

   micropython $youropenschcdirectory/src/test_newschc.py --context \
   example/context-100.json --rule-comp example/comp-rule-100.json \
   --rule-fragin example/frag-rule-101.json --rule-fragout \
   example/frag-rule-102.json --data-file test/icmpv6.dmp \
   --loss-mode list --loss-param 1,2

