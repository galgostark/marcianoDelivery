### This is a web service for use with App
### Inventor for Android (<http://appinventor.googlelabs.com>)
### This particular service stores and retrieves tag-value pairs 
### using the protocol necessary to communicate with the TinyWebDB
### component of an App Inventor app.

### Author: Lyn Turbak (fturbak asperand wellesley.edu) 
###
### History: 
###
###   This is an extensively modified version of customtinywebdb, 
###   a simple overwriting tag/value table-based DB that was created by 
###   David Wolber (wolber asperand usfca.edu), using sample of Hal Abelson
###   (hal asperand mit.edu)
### 
### Lyn's Nov/Dec 2011 modifications to customtinywebdb: 
### + The key *all_tags* denotes a list of all other keys in the database.
###   It is automatically updated when other keys are stored or deleted.  
### + The key *all_values* can be used by GET to retrieve a list of all values
###   in the same order as the tags in *all_tags*
### + The key *all_timestamps* can be used by GET to retrieve a list of all timestamps
###   in the same order as the tags in *all_tags*
### + The key *all_entries* can be used by GET to retrieve a list of all tag/value/timestamp triples,
###   where a triple is a three-element list. 
### + Storing a (non-special) tag with the special value *delete* deletes the entry with that tag.
### + Storing the tag *all_tags* with the special value *delete* deletes 
###   all entries, except *all_tags* (which is set to the empty list).
### + Storing the tag *all_values*,  *all_timestamps*,  or *all_entries* has no effect.
### + The web interface to the database table has a WriteEntriesToPage button that writes
###   a plain text page with a JSON list of tag/value pairs for each (non-special) tag
###   in the database.  This page can then be saved to a text file. Such a file can
###   be read by AddEntriesFromFile.
### + The web interface to the database table has a AddEntriesFromFile button that reads
###   from a specified file a JSON list of tag/value pairs and stores each value with 
###   the associated tag. If the contents of the file is not a JSON list of tag/value
###   pairs, this button has no effect. 

### [lyn, 2011/11/23: had to use % rather than .format for formatting strings since AppEngine uses Python 2.5
### and .format not added until after that. 

### [lyn, 2011/11/24]: localhost:8080 for some reason will *not* show logging.debug messages, but
###   will show logging.info messages. There might be a workaround (StackOverflow suggests
###   dev_appserver.py --debug), but I've just raised all logging messsages to info level. 
###   Also seems I might be able to go to ~/Desktop/GoogleAppEngineLauncher.app/Contents/Resources/GoogleAppEngine-default.bundle/Contents/Resources/google_appengine/google/appengine/tools/dev_appserver_main.py
###   and change ARG_LOGL_LEVEL in DEFAULT_ARGS from logging.INFO to logging.DEBUG.

### [lyn, 2011/12/04]: Added *all_timestamps*, WriteEntriesToPage and Add EntriesToPage buttons
### and removed stringification of third component in /storeavalue and /getavalue

### [lyn, 2014/11/24,30] Upgraded to python2.7, webapp2, and jinja2
### * Use jinja2 template index.html rather than lots of strings in this file. 
### * Can now use .format rather than %

### [lyn, 2014/12/06] Give more reasonable error messages for AddEntriesFromFile

### [lyn, 2014/12/14] It turns out AppInventor expects top-level strings to have extra quotes
### (or else it won't correctly handled strings with spaces and commas, such as
### "this is a string" or "a,comma,separated,string"). So modified code that returns
### json values to phone and web to do this. This is really a bug in AppInventor,
### and should be fixed, perhaps by returning new JSON_VALUE that does the right thing!
### Note that this only affects top-level strings, and strings within lists are fine. 

import webapp2 # [lyn, 2014/11/24] updating to latest webapp
import jinja2 # [lyn, 2014/11/24] updating to latest templates
import os # [lyn, 2014/11/30] added
import logging
from cgi import escape
# # from google.appengine.ext import webapp
# # from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext import db
# from google.appengine.ext.db import Key
# [lyn, 2014/11/11] No longer works in Python 2.7: 
#   from django.utils import simplejson as json
import json
import time

JINJA_ENVIRONMENT = jinja2.Environment(
   loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
   extensions=['jinja2.ext.autoescape'],
   autoescape=False) # [lyn, 2014/11/12] Turn escape off so table shows. 

allKeysTag = "*all_tags*"
allValuesTag = "*all_values*"
allTimestampsTag = "*all_timestamps*"
allEntriesTag = "*all_entries*"
specialTags = [allKeysTag, allValuesTag, allTimestampsTag, allEntriesTag] 
specialNonAllKeysTags = [allValuesTag, allTimestampsTag, allEntriesTag] 
deleteValue = "*delete*"
# deleteValueQuoted = json.dumps("*delete*") # Same as "\"*delete\""
specialValues = [deleteValue]
serverName = "alltags-deletable-tinywebdb"

class StoredData(db.Model):
  tag = db.StringProperty()
  ## value = db.StringProperty(multiline=True)
  ## defining value as a string property limits individual values to 500
  ## characters.   To remove this limit, define value to be a text
  ## property instead, by commenting out the previous line
  ## and replacing it by this one:
  value = db.TextProperty()
  date = db.DateTimeProperty(required=True, auto_now=True)

class MainPage(webapp2.RequestHandler):
  def get(self):
    self.response.headers['Content-Type'] = 'text/html'
    template = JINJA_ENVIRONMENT.get_template('index.html')
    self.response.write(template.render({"tableEntries":  stored_entries_HTML()}))

########################################
### Implementing the operations
### Each operation is design to respond to the JSON request
### or to the Web form, depending on whether the fmt input to the post
### is json or html.

### Each operation is a class.  The class includes the method that
### actually manipulates the DB, followed by the methods that respond
### to post and to get.

class StoreAValue(webapp2.RequestHandler):

  def store_a_value(self, tag, value):
    logging.info('***info:store_a_value(%s,%s)***' % (tag,value))
    extra_message = ''
    try:
      pythonValue = json.loads(value)  # [lyn, 2011/11/25] Need the loads here to prevent stringification of value. 
                                       # This correctly handles values from AppInventor and inputs on web page entered in JSON form 
      logging.info('***try succeeed for %s***' % value)
    except ValueError:
      extra_message = '''
      {value} is not in not in <a href="http://www.w3schools.com/json/json_syntax.asp">JSON form</a>.
      Treating it as if it were entered as "{value}".<br><br>
      '''.format(value=value)
      pythonValue = value # This is a fallback when input on web page is not in JSON form. Treat it as plain string. 
      logging.info('***try failed for %s***' % value)
    if tag in specialNonAllKeysTags: 
      # Do not allow storing anything in *all_values*, *all_timestamps*, or *all_entries*
      WritePhoneOrWeb(self, '', lambda : json.dump(["CANNOT_STORE", tag, pythonValue], self.response.out))
    else: 
      ## Treat storing of the value "*delete*" as deleting a value
      if pythonValue == deleteValue: 
        self.delete_tag(tag)
      elif tag == allKeysTag: ## Ignore an attempt to store any value other than *delete* at *all_tags*, 
        WritePhoneOrWeb(self, '', lambda : json.dump(["CANNOT_STORE", tag, pythonValue], self.response.out))
      else: 
        self.store_a_regular_value(tag, json.dumps(pythonValue), pythonValue, extra_message)

  def store_a_regular_value(self, tag, stringValue, pythonValue, prolog):
    ## There are potential readers/writers errors here :(
    allKeysEntry = db.GqlQuery("SELECT * FROM StoredData where tag = :1", allKeysTag).get()
    if allKeysEntry:
      keyListString = allKeysEntry.value
      keyList = json.loads(keyListString)
      if not tag in keyList: # avoid duplicates
         keyList.append(tag)
         keyList.sort()  # keep key list sorted (could use insertion to be more efficient)
         allKeysEntry.value = json.dumps(keyList) # only update text rep of value if there's a new key
         allKeysEntry.put()
    else: 
      singletonList = [tag]
      allKeysEntry = StoredData(tag = allKeysTag, value = json.dumps(singletonList)) # text rep of list with single key
      allKeysEntry.put()
    entry = db.GqlQuery("SELECT * FROM StoredData where tag = :1", tag).get()
    if entry:
      entry.value = stringValue
    else: 
      entry = StoredData(tag = tag, value = stringValue)
    entry.put()
    ## Send back a confirmation message.  The TinyWebDB component ignores
    ## the message (other than to note that it was received), but other
    ## components might use this.
    result = ["STORED", tag, pythonValue]
    if self.request.get('fmt') == "html":
      result = escapeJSON(result) # escape HTML markers 
    WritePhoneOrWeb(self, prolog, lambda : json.dump(result, self.response.out))
  
  def delete_tag(self, tag):
    ## Treat deleting the allKeys tag as a command to delete all tags
    logging.info('info:delete_tag(%s)\n' % (tag))
    if tag == allKeysTag:
      self.delete_all_tags()
    else:
      self.delete_regular_tag(tag)

  def delete_regular_tag(self, tag):
    ## There are potential readers/writers errors here :(

    ## Delete tag from database
    entry = db.GqlQuery("SELECT * FROM StoredData where tag = :1", tag).get()
    if entry:
      entry_key_string = str(entry.key())
      key = db.Key(entry_key_string)
      db.run_in_transaction(dbSafeDelete,key)

    ## Delete tag from key list
    allKeysEntry = db.GqlQuery("SELECT * FROM StoredData where tag = :1", allKeysTag).get()
    if allKeysEntry:
      keyListString = allKeysEntry.value
      keyList = json.loads(keyListString)
      if tag in keyList: 
         keyList.remove(tag)
         allKeysEntry.value = json.dumps(keyList) # only update text rep of value if there's a new key
         allKeysEntry.put()

    ## Return a JSON result
    result = ["STORED", tag, deleteValue]
    if self.request.get('fmt') == "html":
      result = escapeJSON(result) # escape HTML markers 
    WritePhoneOrWeb(self, '', lambda : json.dump(result, self.response.out))

  def delete_all_tags(self):
    entries = StoredData.all().order("-tag")
    for e in entries:
      entry_key_string = str(e.key())
      tag = escape(e.tag)
      value = escape(e.value)
      if tag == allKeysTag:
         e.value = json.dumps([])
         e.put()
      else:
        key = db.Key(entry_key_string)
        db.run_in_transaction(dbSafeDelete,key)

    ## Return a JSON result
    result = ["STORED", allKeysTag, deleteValue]
    if self.request.get('fmt') == "html":
      result = escapeJSON(result) # escape HTML markers 
    WritePhoneOrWeb(self, '', lambda : json.dump(result, self.response.out))

  def post(self):
    tag = self.request.get('tag')
    value = self.request.get('value')
    self.store_a_value(tag, value)

  def get(self):
    self.response.out.write('''
    <html><body>
    <form action="/storeavalue" method="post"
          enctype=application/x-www-form-urlencoded>
       <p>Tag:&nbsp;<input type="text" name="tag" /> (A tag is a string, but it should *not* be enclosed in quotes --- e.g., color rather than "color" or 'color'.)</p>
       <p>Value:&nbsp;<input type="text" name="value" /> (You must use <a href="http://www.w3schools.com/json/json_syntax.asp">JSON encoding</a> for values -- e.g., "red" rather than red or 'red', [1, "two"] rather than [1, two], etc. Use the special value "*delete*" to delete an entry.) </p>
       <input type="hidden" name="fmt" value="html">
       <input type="submit" value="Store a value">
    </form></body></html>\n''')

class GetValue(webapp2.RequestHandler):

  def get_value(self, tag):
    logging.info('info:get_value(%s)\n' % tag)
    if tag == allValuesTag:
      pythonValue = self.allValuesValue()
    elif tag == allTimestampsTag:
      pythonValue = self.allTimestampsValue()
    elif tag == allEntriesTag:
      pythonValue = self.allEntriesValue()
    else:
      entry = db.GqlQuery("SELECT * FROM StoredData where tag = :1", tag).get()
      if entry:
        pythonValue = json.loads(entry.value)
      else: 
        if tag == allKeysTag:
          pythonValue = []
        else: 
          pythonValue = ""
    ## We tag the returned result with "VALUE".  The TinyWebDB
    ## component makes no use of this, but other programs might.
    ## check if it is a html request and if so clean the tag and value variables
    # logging.info("self.request.get('fmt') = %s" % self.request.get('fmt'))
    # [lyn, 2014/12/14] It turns out AppInventor expects top level strings to have extra quotes
    # (or else it won't correctly handled strings with spaces and commas). Take care of this here.
    result = ["VALUE", tag, addExtraQuotesExpectedByAppInventor(pythonValue)]
    if self.request.get('fmt') == "html":
      result = escapeJSON(result) # escape HTML markers 
      # logging.info('escapeJSON(result) = %s' % result)
    WritePhoneOrWeb(self, '', lambda : json.dump(result, self.response.out))

  # Returns a list of values for all the tags in *all_keys* (which do not include special tags).
  def allValuesValue(self):
    # logging.info("allValuesValue")
    entries = StoredData.all().order("tag") # Orders lo to hi. Use "-tag" to order from hi to lo
    result = [] 
    for e in entries:
      if e.tag != allKeysTag: 
        # logging.info('allValuesValue: entry tag = ' + e.tag + '; entry value = ' + e.value)
        pythonValue = json.loads(e.value)
        # logging.info('allValuesValue: pythonValue = ' + str(pythonValue))
        result.append(pythonValue)
    return result

  # Returns a list of timestamps for all the tags in *all_keys* (which do not include special tags).
  def allTimestampsValue(self):
    entries = StoredData.all().order("tag") # Orders lo to hi. Use "-tag" to order from hi to lo
    result = [] 
    for e in entries:
      if e.tag != allKeysTag: 
#        result.append(e.date.ctime())
         result.append(timeString(e.date))
    return result

  # Returns a list of all tag/value/timestamp triples, 
  # where a triple is a three-element list [<key>,<value>,<timestamp>]
  # The keys do not include special tags.
  def allEntriesValue(self):
    entries = StoredData.all().order("tag") # Orders lo to hi. Use "-tag" to order from hi to lo
    result = [] 
    for e in entries:
      if e.tag != allKeysTag: 
#       result.append([e.tag,json.loads(e.value),e.date.ctime()])
        result.append([e.tag,json.loads(e.value),timeString(e.date)])
    return result

  def post(self):
    tag = self.request.get('tag')
    self.get_value(tag)

  def get(self):
    self.response.out.write('''
    <html><body>
    <form action="/getvalue" method="post"
          enctype=application/x-www-form-urlencoded>
       <p>Tag:&nbsp;<input type="text" name="tag" /> (A tag is a string, but it should *not* be enclosed in quotes --- e.g., color rather than "color" or 'color'. Special tags are *all_tags*, *all_values*, *all_timestamps*, and *all_entries".)</p>
       <input type="hidden" name="fmt" value="html">
       <input type="submit" value="Get value">
    </form></body></html>\n''')

# # Lyn: deletion now performed by storing "*delete*". 
# # The DeleteEntry is called from the Web only, by pressing one of the
# # buttons on the main page.  So there's no get method, only a post.

class DeleteEntry(webapp2.RequestHandler):

  def post(self):
    logging.info('/deleteentry?%s\n|%s|' %
                  (self.request.query_string, self.request.body))
    entry_key_string = self.request.get('entry_key_string')
    key = db.Key(entry_key_string)
    # tag = self.request.get('tag')
    db.run_in_transaction(dbSafeDelete,key)
    self.redirect('/')

# Write the contents of a table to a web page.
class WriteEntries(webapp2.RequestHandler):

  def post(self):
    entries = StoredData.all().order("tag") # Orders lo to hi. Use "-tag" to order from hi to lo
    # entries does not appear to be a list, so must convert it to one first 
    entryList = []
    for e in entries:
      if e.tag != allKeysTag: # Don't put this key in table; it's implicit 
        entryList.append([e.tag, json.loads(e.value)]) # tag/value pair, where tag is string
    # Write contents of JSON entry list to new web page as text. 
    # Users can easily save this away in a text file. 
    self.response.headers['Content-Type'] = 'text/plain'
    writeJSONEntryList(self, entryList, "txt")

# Read the contents of a file containing a json list of tag/value pairs
# and add these to the table. 
class AddEntries(webapp2.RequestHandler):

  def addEntries(self, jsonEntries):
    ## There are potential readers/writers errors here :(

    ## First, update *all_tags* key list
    allKeysEntry = db.GqlQuery("SELECT * FROM StoredData where tag = :1", allKeysTag).get()
    if allKeysEntry:
      keyListString = allKeysEntry.value
      keyList = json.loads(keyListString)
    else: 
      keyList = []
    allTags = map(lambda pair: pair[0], 
                  filter(lambda pair: pair[0] not in specialTags and pair[1] not in specialValues,
                         jsonEntries))
    newTags = filter(lambda tag: tag not in keyList, allTags)
    keyList.extend(newTags) # Add new tags to list
    keyList.sort()  # keep key list sorted 
    if allKeysEntry:
      allKeysEntry.value = json.dumps(keyList) # only update text rep of value if there's a new key
    else: 
      allKeysEntry = StoredData(tag = allKeysTag, value = json.dumps(keyList)) # 
    allKeysEntry.put() # Store updated key list 

    ## Next, store each tag/value pair in table. 
    for entryPair in jsonEntries:
      tag = entryPair[0]
      value = entryPair[1]
      if tag not in specialTags and value not in specialValues:
        stringValue = json.dumps(value)
        entry = db.GqlQuery("SELECT * FROM StoredData where tag = :1", tag).get()
        if entry:
          entry.value = stringValue
        else: 
          entry = StoredData(tag = tag, value = stringValue)
        entry.put()

    ## Finally, write in web pages json list of all entry pairs. 
    self.response.headers['Content-Type'] = 'text/html'
    self.response.out.write('<html><body>') 
    self.response.out.write('''
    Entries from this entry list have been added to the database:<br>
    ''')
    writeJSONEntryList(self, escapeJSON(jsonEntries), "html")
    self.response.out.write('''<br>
    <p><a href="/">
    <i>Return to {serverName} TinyWebDB Main Page</i>
    </a><br><br>
    '''.format(serverName=serverName))
    self.response.out.write('</body></html>')

  def post(self):
    # self.response.out.write("add entries")
    entriesString = self.request.get("entriesFile") # Contents of entries file. Should be in json format
    logging.info('***info:entriesFile = %s)***' % entriesString)
    try: 
      entriesValue = json.loads(entriesString)
      verifyTagValuePairs(entriesValue) # Raises error if there is a problem; otherwise just returns
      self.addEntries(entriesValue)
    except ValueError as valerror: 
      self.fileError(entriesString, valerror)
    except Exception as exc: 
      self.fileError(entriesString, exc)

  def fileError(self, entriesString, error):
    valErrorType = type(ValueError('foo'))
    exceptionType = type(Exception('foo'))
    self.response.headers['Content-Type'] = 'text/html'
    if entriesString == "":
      self.response.out.write('Entries list file is empty! Perhaps you forgot to Choose a file?<br>')
    elif type(error) == valErrorType: 
      self.response.out.write('Entries list file is not well-formed JSON.<br>It must be a JSON list of tag/value pairs.<br><br>')
      self.response.out.write(entriesString)
    elif type(error) == exceptionType: 
      entriesValue = json.loads(entriesString)
      args = error.args
      msg = args[0]
      if msg == 'database_not_a_list':
        self.response.out.write('Entries are not a list.<br>They must be a JSON list of tag/value pairs.<br><br>')
        self.response.out.write(entriesString)
      elif msg == 'entry_not_a_list': 
        self.entryError(args[1], entriesValue, 
                   'Entry is not a list.<br>It must be a two-element list of tag (string) and value.')
      elif msg == 'entry_not_a_pair': 
        self.entryError(args[1], entriesValue, 
                   'Malformed entry.<br>It must be a two-element list of tag (string) and value, but this entry is a list with ' + str(len(args[1])) + ' elements.')
      elif msg == 'entry_tag_not_a_string': 
        self.entryError(args[1], entriesValue, 
                   'In an entry (tag/value pair), the tag (first element) must be a string, but ' + str(args[1][0]) + ' is not a string.')
      else:           
        self.unexpectedError(error, entriesValue)
    else:           
      self.unexpectedError(error, entriesString)
    self.response.out.write('''<br>
    <p><a href="/">
    <i>Return to {serverName} TinyWebDB Main Page</i>
    </a><br><br>
    '''.format(serverName=serverName))
    self.response.out.write('</body></html>')

  def entryError(self, entry, entries, msg):
    self.response.out.write(msg + '<br><br>Entry:<br>')
    self.response.out.write(entry)
    self.response.out.write('<br><br>Entries list:<br>')
    writeJSONEntryList(self, escapeJSON(entries), "html")

  def unexpectedError(self, error, entriesStringOrValue):
    self.response.out.write('Unexpected error in AddEntries.<br><br>')
    self.response.out.write('Error type: ' + str(type(error)) + '<br><br>')
    self.response.out.write('Error args:<br><br>')
    args = error.args
    for i in range(len(args)):
      self.response.out.write('args[' + str(i) + ']<br>')
      self.response.out.write(str(args[i]))
      self.response.out.write('<br><br>')
    if isString(entriesStringOrValue):
      self.response.out.write('Entries:<br>')
      self.response.out.write(entriesStringOrValue)
    else: 
      self.response.out.write('Entries list:<br>')
      writeJSONEntryList(self, escapeJSON(entriesStringOrValue), "html")

# ########################################
# #### Procedures used in displaying the main page

# Return time as MM/DD/YYYY hh:mm:ss, the format required by Clock.MakeInstant from
def timeString (time): 
  return time.strftime("%m/%d/%Y %H:%M:%S")

def writeJSONEntryList(self, entryList, format):
  newlineString = "<br>"
  if format == "txt":
    newlineString = "\n"
  self.response.out.write('[%s' % newlineString) # begin list of entries.
  # [lyn, 12/4/2011] Following simple code puts comma after last entry, which json.loads doesn't like
  # for pair in entryList:
  #   self.response.out.write('%s,\n' % json.dumps(pair)) # write tag/value pair, one per line. 
  maxIndex = len(entryList) - 1 # indices start at 0, not 1
  index = 0
  for pair in entryList:
    self.response.out.write(json.dumps(pair)) # write tag/value pair, one per line. 
    if index != maxIndex:
      self.response.out.write(",")
    self.response.out.write(newlineString)
    index = index + 1
  self.response.out.write(']') # end list of entries.

### Show the tags and values as a table.
def stored_entries_HTML():

  def HTMLEntry (tag, value, timestamp, hasDeleteButton):
    # logging.info("HTMLEntry(" + tag + "," + value + "," + timestamp + "," + str(hasDeleteButton))
    deleteButtonHTML = '<td></td>\n' # No delete button
    if hasDeleteButton: 
      deleteButtonHTML = '''
        <td>
          <form action="/storeavalue" method="post"
                enctype=application/x-www-form-urlencoded>
            <input type="hidden" name="tag" value="{tag}">
	    <input type="hidden" name="value" value="{deleteValue}">
            <input type="hidden" name="fmt" value="html">
	    <input type="submit" style="background-color: red" value="Delete">
          </form>
        </td>\n
        '''.format(tag=tag, deleteValue=deleteValue)

    entryHTML = '''
      <tr>
        <td>{tag}</td>
        <td>{value}</td>
        <td><font size="-1">{timestamp}</font></td>
        {deleteButton}
      </tr>
      '''.format(tag=tag, value=value, timestamp=timestamp, deleteButton=deleteButtonHTML)

    return entryHTML

  ### AllKeys entry
  allKeysEntry = db.GqlQuery("SELECT * FROM StoredData where tag = :1", allKeysTag).get()
  if allKeysEntry:
    allKeysValue = allKeysEntry.value
#   allKeysTime = allKeysEntry.date.ctime()
    allKeysTime = timeString(allKeysEntry.date)
  else:
    allKeysValue = json.dumps([])
    allKeysTime = ""

  # Special quadruples
  quadruples = [[allKeysTag, allKeysValue, allKeysTime, True], 
                [allValuesTag, '<i>A list of all values, in the same order as all tags</i>', '', False], 
                [allTimestampsTag, '<i>A list of all timestamps, in the same order as all tags</i>', '', False], 
                [allEntriesTag, '<i>A list of all tag/value/timestamp triples</i>', '', False]]

  # Stored tag/value entries
  # This next line is replaced by the one under it, in order to help
  # protect against SQL injection attacks.  Does it help enough?
  entries = db.GqlQuery("SELECT * FROM StoredData ORDER BY tag")
# keyValueQuadruples = [[escape(e.tag), escape(e.value), e.date.ctime(), True] 
  keyValueQuadruples = [[escape(e.tag), escape(e.value), timeString(e.date), True] 
                        for e in entries
                        if e.tag != allKeysTag] # We've already shown all keys above 

  quadruples.extend(keyValueQuadruples)
  # logging.info("entries=" + str(entries))
  return ''.join([HTMLEntry(q[0], q[1], q[2], q[3]) for q in quadruples])

#### Utilty procedures for generating the output

#### Write response to the phone or to the Web depending on fmt
#### Handler is an appengine request handler.  writer is a thunk
#### (i.e. a procedure of no arguments) that does the write when invoked.
def WritePhoneOrWeb(handler, prolog, writer):
  if handler.request.get('fmt') == "html":
    WritePhoneOrWebToWeb(handler, prolog, writer) # Only write prolog on web page 
  else:
    handler.response.headers['Content-Type'] = 'application/jsonrequest'
    writer()

#### Result when writing to the Web
def WritePhoneOrWebToWeb(handler, prolog, writer):
  handler.response.headers['Content-Type'] = 'text/html'
  handler.response.out.write('<html><body>')
  handler.response.out.write(prolog)
  handler.response.out.write('''
  <em>The server will send this to the component:</em>
  <p />''')
  writer()
  WriteWebFooter(handler, writer)

def WriteWebFooter(handler, writer):
  handler.response.out.write('''
  <p><a href="/">
  <i>Return to %s TinyWebDB Main Page</i>
  </a>''' % serverName)
  handler.response.out.write('</body></html>')

### A utility that guards against attempts to delete a non-existent object
def dbSafeDelete(key):
  if db.get(key) :  db.delete(key)

### Escape HTML markup within strings within a JSON value
listType = type([])
dictType = type({})
stringType = type("foo") # Could be <type 'str'> or <type 'unicode'>
jsonStringType = type(json.loads(json.dumps("foo")))

def isString(thing): 
  typ = type(thing)
  return typ == stringType or typ == jsonStringType

# Bizarrely, AppInventor mishandles top-level strings returned by TinyWebDB
# which, due to an unnecessary extra level of interpretation, it requires to 
# be wrapped in an extra set of double quotes. Until this is fixed, it is 
# necessary for TinyWebDB to return top-level strings with these extra quotes.
# Note that strings nested in lists need not be handled in this way. 
def addExtraQuotesExpectedByAppInventor(pythonValue):
  if isString(pythonValue):
    return "\"" + pythonValue + "\""
  else:
    return pythonValue

def escapeJSON(jsonValue):
  typ = type(jsonValue)
  # logging.info("escapeJSON(%s); typ = %s" % (jsonValue, typ))
  if typ == jsonStringType:
    return escape(jsonValue) # Escape HTML markup in strings
  elif typ == listType:
    return map (escapeJSON, jsonValue)
  elif typ == dictType:
    return dict(map (lambda item: [item[0], escapeJSON(item[1])], jsonValue.items()))
  else:
    return jsonValue # Return other values unchanged (including base type values and objects/functions)

## Check that a database specification has the form of tag/value pairs. 
## Raise an exception when it does not.
def verifyTagValuePairs(database):
  if type(database) != listType:
    raise Exception('database_not_a_list', database)
  else:
    for entry in database:
      if type(entry) != listType:
        raise Exception('entry_not_a_list', entry, database)
      elif len(entry) != 2: 
        raise Exception('entry_not_a_pair', entry, database)
      elif not(isString(entry[0])):
        raise Exception('entry_tag_not_a_string', entry, database)
  # Get here only if all entries valid

### Assign the classes to the URLs

application = webapp2.WSGIApplication([
    ('/', MainPage),
    ('/storeavalue', StoreAValue),
    ## To delete, use /storeavalue with *delete* as value
    ## ('/deleteentry', DeleteEntry),
    ('/getvalue', GetValue),
    ('/addentries', AddEntries),
    ('/writeentries', WriteEntries)
], debug=True)

# [lyn, 2014/11/11] Remove these for webapp2
# def main():
#   run_wsgi_app(application)
#
# if __name__ == '__main__':
#   main()

### Copyright 2009 Google Inc.
###
### Licensed under the Apache License, Version 2.0 (the "License");
### you may not use this file except in compliance with the License.
### You may obtain a copy of the License at
###
###     http://www.apache.org/licenses/LICENSE-2.0
###
### Unless required by applicable law or agreed to in writing, software
### distributed under the License is distributed on an "AS IS" BASIS,
### WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
### See the License for the specific language governing permissions and
### limitations under the License.
###
