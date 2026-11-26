# Stage 1 Evidence

Captured from real runs on the branch before the Stage 1 commit. Python: Python 3.11.15

## `../.venv/bin/python -m pytest -q`

```
........................................................................ [ 50%]
........................................................................ [100%]
144 passed in 13.69s
exit code: 0
```

## Samples fail before revival

```
    return 0755
           ^
SyntaxError: leading zeros in decimal integer literals are not permitted; use an 0o prefix for octal integers
sample-legacy-1 exit: 1
  File "/projects/sandbox/The-Grimoire/samples/sample-legacy-2/main.py", line 2, in <module>
    import ConfigParser
ModuleNotFoundError: No module named 'ConfigParser'
sample-legacy-2 exit: 1
```

## `../.venv/bin/python -m grimoire autopsy samples/sample-legacy-1`

```
CAUSE OF DEATH
  SYNTAX: 10
COVERAGE
  python: ANALYZED (1 file(s))
FINDINGS
  [ERROR] [AUTOMATIC] BUILTINS main.py:10 Python 2 construct handled by rule BUILTINS
  [ERROR] [AUTOMATIC] BUILTINS main.py:15 Python 2 construct handled by rule BUILTINS
  [ERROR] [AUTOMATIC] DICT_METHODS main.py:21 Python 2 construct handled by rule DICT_METHODS
  [ERROR] [AUTOMATIC] DICT_METHODS main.py:24 Python 2 construct handled by rule DICT_METHODS
  [ERROR] [AUTOMATIC] EXCEPT_AS main.py:32 Python 2 construct handled by rule EXCEPT_AS
  [ERROR] [AUTOMATIC] PRINT_STMT main.py:33 Python 2 construct handled by rule PRINT_STMT
  [ERROR] [AUTOMATIC] OCTAL_LITERAL main.py:39 Python 2 construct handled by rule OCTAL_LITERAL
  [ERROR] [AUTOMATIC] PRINT_STMT main.py:44 Python 2 construct handled by rule PRINT_STMT
  [ERROR] [AUTOMATIC] NE_OPERATOR main.py:48 Python 2 construct handled by rule NE_OPERATOR
  [ERROR] [AUTOMATIC] PRINT_STMT main.py:50 Python 2 construct handled by rule PRINT_STMT
exit code: 0
```

## `../.venv/bin/python -m grimoire autopsy samples/sample-legacy-2`

```
CAUSE OF DEATH
  DEPENDENCY: 5
  IMPORT: 4
COVERAGE
  python: ANALYZED (1 file(s))
FINDINGS
  [ERROR] [AUTOMATIC] OUTDATED_IMPORT main.py:2 ConfigParser was removed or renamed in Python 3; use configparser
  [ERROR] [AUTOMATIC] OUTDATED_IMPORT main.py:3 Queue was removed or renamed in Python 3; use queue
  [ERROR] [AUTOMATIC] OUTDATED_IMPORT main.py:4 urllib2 was removed or renamed in Python 3; use urllib.request
  [ERROR] [AUTOMATIC] OUTDATED_IMPORT main.py:5 StringIO was removed or renamed in Python 3; use io
  [ERROR] [AUTOMATIC] MISSING_DEPENDENCY main.py:7 'six' is imported but six is not declared in any manifest
  [WARNING] [AUTOMATIC] RENAMED_PACKAGE requirements.txt:1 beautifulsoup was renamed on PyPI; now beautifulsoup4
  [ERROR] [AUTOMATIC] REMOVED_PACKAGE requirements.txt:2 distribute is obsolete on Python 3.11 (stdlib or dead backport); line dropped
  [ERROR] [AUTOMATIC] REMOVED_PACKAGE requirements.txt:3 ordereddict is obsolete on Python 3.11 (stdlib or dead backport); line dropped
  [WARNING] [AUTOMATIC] DUPLICATE_REQUIREMENT requirements.txt:4 beautifulsoup4 is already declared; duplicate dropped
exit code: 0
```

## `../.venv/bin/python -m grimoire revive samples/sample-legacy-1 --output /tmp/out1`

```
BEFORE
  [ERROR] [AUTOMATIC] BUILTINS main.py:10 Python 2 construct handled by rule BUILTINS
  [ERROR] [AUTOMATIC] BUILTINS main.py:15 Python 2 construct handled by rule BUILTINS
  [ERROR] [AUTOMATIC] DICT_METHODS main.py:21 Python 2 construct handled by rule DICT_METHODS
  [ERROR] [AUTOMATIC] DICT_METHODS main.py:24 Python 2 construct handled by rule DICT_METHODS
  [ERROR] [AUTOMATIC] EXCEPT_AS main.py:32 Python 2 construct handled by rule EXCEPT_AS
  [ERROR] [AUTOMATIC] PRINT_STMT main.py:33 Python 2 construct handled by rule PRINT_STMT
  [ERROR] [AUTOMATIC] OCTAL_LITERAL main.py:39 Python 2 construct handled by rule OCTAL_LITERAL
  [ERROR] [AUTOMATIC] PRINT_STMT main.py:44 Python 2 construct handled by rule PRINT_STMT
  [ERROR] [AUTOMATIC] NE_OPERATOR main.py:48 Python 2 construct handled by rule NE_OPERATOR
  [ERROR] [AUTOMATIC] PRINT_STMT main.py:50 Python 2 construct handled by rule PRINT_STMT
REPAIRS APPLIED
  main.py: PRINT_STMT, EXCEPT_AS, NE_OPERATOR, OCTAL_LITERAL, BUILTINS, DICT_METHODS
REPAIRS REJECTED
  none
REMAINING (manual or unsupported)
  none
VALIDATION
  PASS: all Python files parse
  PASS: no unresolved findings
DIFF
--- a/main.py
+++ b/main.py
@@ -7,21 +7,21 @@

 def ask(prompt):
     """Interactive helper kept from the original shell front end (not used by the demo)."""
-    return raw_input(prompt)
+    return input(prompt)


 def load_sales():
     sales = {}
-    for i in xrange(1, 6):
+    for i in range(1, 6):
         sales["item%d" % i] = i * 3
     return sales


 def total(sales):
-    if not sales.has_key("item1"):
+    if "item1" not in sales:
         raise ValueError("no item1 in sales")
     amount = 0
-    for name, qty in sales.iteritems():
+    for name, qty in sales.items():
         amount = amount + qty
     return amount

@@ -29,25 +29,25 @@
 def parse_quantity(text):
     try:
         return int(text)
-    except ValueError, e:
-        print "bad quantity: %s" % e
+    except ValueError as e:
+        print("bad quantity: %s" % e)
         return 0


 def report_mode():
     # Unix permission bits, written as an old-style octal literal.
-    return 0755
+    return 0o755


 def main():
     sales = load_sales()
-    print "TALLY KEEPER"
-    print "total units:", total(sales)
-    print "bad input gives", parse_quantity("abc")
-    print "report mode: %o" % report_mode()
-    if total(sales) <> 45:
+    print("TALLY KEEPER")
+    print("total units:", total(sales))
+    print("bad input gives", parse_quantity("abc"))
+    print("report mode: %o" % report_mode())
+    if total(sales) != 45:
         sys.exit(1)
-    print "TALLY KEEPER ALIVE"
+    print("TALLY KEEPER ALIVE")


 if __name__ == "__main__":
exit code: 0
```

## `../.venv/bin/python -m grimoire revive samples/sample-legacy-2 --output /tmp/out2`

```
BEFORE
  [ERROR] [AUTOMATIC] OUTDATED_IMPORT main.py:2 ConfigParser was removed or renamed in Python 3; use configparser
  [ERROR] [AUTOMATIC] OUTDATED_IMPORT main.py:3 Queue was removed or renamed in Python 3; use queue
  [ERROR] [AUTOMATIC] OUTDATED_IMPORT main.py:4 urllib2 was removed or renamed in Python 3; use urllib.request
  [ERROR] [AUTOMATIC] OUTDATED_IMPORT main.py:5 StringIO was removed or renamed in Python 3; use io
  [ERROR] [AUTOMATIC] MISSING_DEPENDENCY main.py:7 'six' is imported but six is not declared in any manifest
  [WARNING] [AUTOMATIC] RENAMED_PACKAGE requirements.txt:1 beautifulsoup was renamed on PyPI; now beautifulsoup4
  [ERROR] [AUTOMATIC] REMOVED_PACKAGE requirements.txt:2 distribute is obsolete on Python 3.11 (stdlib or dead backport); line dropped
  [ERROR] [AUTOMATIC] REMOVED_PACKAGE requirements.txt:3 ordereddict is obsolete on Python 3.11 (stdlib or dead backport); line dropped
  [WARNING] [AUTOMATIC] DUPLICATE_REQUIREMENT requirements.txt:4 beautifulsoup4 is already declared; duplicate dropped
REPAIRS APPLIED
  main.py: OUTDATED_IMPORT
  requirements.txt: REQUIREMENTS
REPAIRS REJECTED
  none
REMAINING (manual or unsupported)
  none
VALIDATION
  PASS: all Python files parse
  PASS: no unresolved findings
DIFF
--- a/main.py
+++ b/main.py
@@ -1,8 +1,8 @@
 """Lost Ledger: reads a ledger settings file and queues entries (Python 2 module names)."""
-import ConfigParser
-import Queue
-import urllib2
-from StringIO import StringIO
+import configparser
+import queue
+import urllib.request, urllib.error
+from io import StringIO

 import six

@@ -14,13 +14,13 @@


 def load_settings(text):
-    parser = ConfigParser.SafeConfigParser()
+    parser = configparser.ConfigParser()
     parser.readfp(StringIO(text))
     return parser.get("ledger", "name"), parser.getint("ledger", "entries")


 def queue_entries(count):
-    q = Queue.Queue()
+    q = queue.Queue()
     for n in range(count):
         q.put("entry-%d" % n)
     return q
@@ -28,7 +28,7 @@

 def is_network_error(exc):
     # Only the exception classes are used; no request is ever made.
-    return isinstance(exc, urllib2.URLError)
+    return isinstance(exc, urllib.error.URLError)


 def main():
--- a/requirements.txt
+++ b/requirements.txt
@@ -1,4 +1,2 @@
-beautifulsoup
-distribute>=0.6
-ordereddict==1.1
 beautifulsoup4
+six
exit code: 0
```

## `../.venv/bin/python -m grimoire prove samples/sample-legacy-1`

```
BEFORE
  [ERROR] [AUTOMATIC] BUILTINS main.py:10 Python 2 construct handled by rule BUILTINS
  [ERROR] [AUTOMATIC] BUILTINS main.py:15 Python 2 construct handled by rule BUILTINS
  [ERROR] [AUTOMATIC] DICT_METHODS main.py:21 Python 2 construct handled by rule DICT_METHODS
  [ERROR] [AUTOMATIC] DICT_METHODS main.py:24 Python 2 construct handled by rule DICT_METHODS
  [ERROR] [AUTOMATIC] EXCEPT_AS main.py:32 Python 2 construct handled by rule EXCEPT_AS
  [ERROR] [AUTOMATIC] PRINT_STMT main.py:33 Python 2 construct handled by rule PRINT_STMT
  [ERROR] [AUTOMATIC] OCTAL_LITERAL main.py:39 Python 2 construct handled by rule OCTAL_LITERAL
  [ERROR] [AUTOMATIC] PRINT_STMT main.py:44 Python 2 construct handled by rule PRINT_STMT
  [ERROR] [AUTOMATIC] NE_OPERATOR main.py:48 Python 2 construct handled by rule NE_OPERATOR
  [ERROR] [AUTOMATIC] PRINT_STMT main.py:50 Python 2 construct handled by rule PRINT_STMT
REPAIRS APPLIED
  main.py: PRINT_STMT, EXCEPT_AS, NE_OPERATOR, OCTAL_LITERAL, BUILTINS, DICT_METHODS
REPAIRS REJECTED
  none
REMAINING (manual or unsupported)
  none
VALIDATION
  PASS: all Python files parse
  PASS: no unresolved findings
PROOF: ALIVE
  TALLY KEEPER
  total units: 45
  bad quantity: invalid literal for int() with base 10: 'abc'
  bad input gives 0
  report mode: 755
  TALLY KEEPER ALIVE
DIFF
--- a/main.py
+++ b/main.py
@@ -7,21 +7,21 @@

 def ask(prompt):
     """Interactive helper kept from the original shell front end (not used by the demo)."""
-    return raw_input(prompt)
+    return input(prompt)


 def load_sales():
     sales = {}
-    for i in xrange(1, 6):
+    for i in range(1, 6):
         sales["item%d" % i] = i * 3
     return sales


 def total(sales):
-    if not sales.has_key("item1"):
+    if "item1" not in sales:
         raise ValueError("no item1 in sales")
     amount = 0
-    for name, qty in sales.iteritems():
+    for name, qty in sales.items():
         amount = amount + qty
     return amount

@@ -29,25 +29,25 @@
 def parse_quantity(text):
     try:
         return int(text)
-    except ValueError, e:
-        print "bad quantity: %s" % e
+    except ValueError as e:
+        print("bad quantity: %s" % e)
         return 0


 def report_mode():
     # Unix permission bits, written as an old-style octal literal.
-    return 0755
+    return 0o755


 def main():
     sales = load_sales()
-    print "TALLY KEEPER"
-    print "total units:", total(sales)
-    print "bad input gives", parse_quantity("abc")
-    print "report mode: %o" % report_mode()
-    if total(sales) <> 45:
+    print("TALLY KEEPER")
+    print("total units:", total(sales))
+    print("bad input gives", parse_quantity("abc"))
+    print("report mode: %o" % report_mode())
+    if total(sales) != 45:
         sys.exit(1)
-    print "TALLY KEEPER ALIVE"
+    print("TALLY KEEPER ALIVE")


 if __name__ == "__main__":
exit code: 0
```

## `../.venv/bin/python -m grimoire prove samples/sample-legacy-2`

```
BEFORE
  [ERROR] [AUTOMATIC] OUTDATED_IMPORT main.py:2 ConfigParser was removed or renamed in Python 3; use configparser
  [ERROR] [AUTOMATIC] OUTDATED_IMPORT main.py:3 Queue was removed or renamed in Python 3; use queue
  [ERROR] [AUTOMATIC] OUTDATED_IMPORT main.py:4 urllib2 was removed or renamed in Python 3; use urllib.request
  [ERROR] [AUTOMATIC] OUTDATED_IMPORT main.py:5 StringIO was removed or renamed in Python 3; use io
  [ERROR] [AUTOMATIC] MISSING_DEPENDENCY main.py:7 'six' is imported but six is not declared in any manifest
  [WARNING] [AUTOMATIC] RENAMED_PACKAGE requirements.txt:1 beautifulsoup was renamed on PyPI; now beautifulsoup4
  [ERROR] [AUTOMATIC] REMOVED_PACKAGE requirements.txt:2 distribute is obsolete on Python 3.11 (stdlib or dead backport); line dropped
  [ERROR] [AUTOMATIC] REMOVED_PACKAGE requirements.txt:3 ordereddict is obsolete on Python 3.11 (stdlib or dead backport); line dropped
  [WARNING] [AUTOMATIC] DUPLICATE_REQUIREMENT requirements.txt:4 beautifulsoup4 is already declared; duplicate dropped
REPAIRS APPLIED
  main.py: OUTDATED_IMPORT
  requirements.txt: REQUIREMENTS
REPAIRS REJECTED
  none
REMAINING (manual or unsupported)
  none
VALIDATION
  PASS: all Python files parse
  PASS: no unresolved findings
PROOF: UNVERIFIED
  dependencies cannot be installed offline without a wheelhouse: beautifulsoup4, six
DIFF
--- a/main.py
+++ b/main.py
@@ -1,8 +1,8 @@
 """Lost Ledger: reads a ledger settings file and queues entries (Python 2 module names)."""
-import ConfigParser
-import Queue
-import urllib2
-from StringIO import StringIO
+import configparser
+import queue
+import urllib.request, urllib.error
+from io import StringIO

 import six

@@ -14,13 +14,13 @@


 def load_settings(text):
-    parser = ConfigParser.SafeConfigParser()
+    parser = configparser.ConfigParser()
     parser.readfp(StringIO(text))
     return parser.get("ledger", "name"), parser.getint("ledger", "entries")


 def queue_entries(count):
-    q = Queue.Queue()
+    q = queue.Queue()
     for n in range(count):
         q.put("entry-%d" % n)
     return q
@@ -28,7 +28,7 @@

 def is_network_error(exc):
     # Only the exception classes are used; no request is ever made.
-    return isinstance(exc, urllib2.URLError)
+    return isinstance(exc, urllib.error.URLError)


 def main():
--- a/requirements.txt
+++ b/requirements.txt
@@ -1,4 +1,2 @@
-beautifulsoup
-distribute>=0.6
-ordereddict==1.1
 beautifulsoup4
+six
exit code: 2
```

## `../.venv/bin/python -m grimoire prove samples/sample-legacy-2 --wheelhouse /tmp/wh`

```
BEFORE
  [ERROR] [AUTOMATIC] OUTDATED_IMPORT main.py:2 ConfigParser was removed or renamed in Python 3; use configparser
  [ERROR] [AUTOMATIC] OUTDATED_IMPORT main.py:3 Queue was removed or renamed in Python 3; use queue
  [ERROR] [AUTOMATIC] OUTDATED_IMPORT main.py:4 urllib2 was removed or renamed in Python 3; use urllib.request
  [ERROR] [AUTOMATIC] OUTDATED_IMPORT main.py:5 StringIO was removed or renamed in Python 3; use io
  [ERROR] [AUTOMATIC] MISSING_DEPENDENCY main.py:7 'six' is imported but six is not declared in any manifest
  [WARNING] [AUTOMATIC] RENAMED_PACKAGE requirements.txt:1 beautifulsoup was renamed on PyPI; now beautifulsoup4
  [ERROR] [AUTOMATIC] REMOVED_PACKAGE requirements.txt:2 distribute is obsolete on Python 3.11 (stdlib or dead backport); line dropped
  [ERROR] [AUTOMATIC] REMOVED_PACKAGE requirements.txt:3 ordereddict is obsolete on Python 3.11 (stdlib or dead backport); line dropped
  [WARNING] [AUTOMATIC] DUPLICATE_REQUIREMENT requirements.txt:4 beautifulsoup4 is already declared; duplicate dropped
REPAIRS APPLIED
  main.py: OUTDATED_IMPORT
  requirements.txt: REQUIREMENTS
REPAIRS REJECTED
  none
REMAINING (manual or unsupported)
  none
VALIDATION
  PASS: all Python files parse
  PASS: no unresolved findings
PROOF: ALIVE
  <tmp>/work/main.py:18: DeprecationWarning: This method will be removed in Python 3.12. Use 'parser.read_file()' instead.
    parser.readfp(StringIO(text))
  Harbour Accounts: 3 queued
  network error check: False
  LOST LEDGER ALIVE
DIFF
--- a/main.py
+++ b/main.py
@@ -1,8 +1,8 @@
 """Lost Ledger: reads a ledger settings file and queues entries (Python 2 module names)."""
-import ConfigParser
-import Queue
-import urllib2
-from StringIO import StringIO
+import configparser
+import queue
+import urllib.request, urllib.error
+from io import StringIO

 import six

@@ -14,13 +14,13 @@


 def load_settings(text):
-    parser = ConfigParser.SafeConfigParser()
+    parser = configparser.ConfigParser()
     parser.readfp(StringIO(text))
     return parser.get("ledger", "name"), parser.getint("ledger", "entries")


 def queue_entries(count):
-    q = Queue.Queue()
+    q = queue.Queue()
     for n in range(count):
         q.put("entry-%d" % n)
     return q
@@ -28,7 +28,7 @@

 def is_network_error(exc):
     # Only the exception classes are used; no request is ever made.
-    return isinstance(exc, urllib2.URLError)
+    return isinstance(exc, urllib.error.URLError)


 def main():
--- a/requirements.txt
+++ b/requirements.txt
@@ -1,4 +1,2 @@
-beautifulsoup
-distribute>=0.6
-ordereddict==1.1
 beautifulsoup4
+six
exit code: 0
```

## Recovered projects run

```
TALLY KEEPER
total units: 45
bad quantity: invalid literal for int() with base 10: 'abc'
bad input gives 0
report mode: 755
TALLY KEEPER ALIVE
exit: 0
```

## Recovered requirements.txt of sample-legacy-2

```
beautifulsoup4
six
```

## Source samples unchanged

```
?? samples/
(only the new untracked sample files before commit; no modifications after the runs)
```
