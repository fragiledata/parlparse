# vim:sw=8:ts=8:et:nowrap

import sys
import re
import os
import string


import mx.DateTime



from splitheadingsspeakers import SplitHeadingsSpeakers
from splitheadingsspeakers import StampUrl

from clsinglespeech import qspeech
from parlphrases import parlPhrases

from miscfuncs import FixHTMLEntities, IsNotQuiet

from filterdivision import FilterDivision
from lordsfilterdivisions import LordsFilterDivision
from lordsfilterdivisions import LordsDivisionParsingPart
from filterdebatespeech import FilterDebateSpeech

from contextexception import ContextException


def StripDebateHeading(hmatch, ih, headspeak, bopt=False):
	reheadmatch = '(?:<stamp aname="[^"]*"/>)*' + hmatch
	if (not re.match(reheadmatch, headspeak[ih][0])) or headspeak[ih][2]:
		if bopt:
			return ih
		print "\n", headspeak[ih]
		raise ContextException('non-conforming "%s" heading ' % hmatch)
	return ih + 1

def StripLordsDebateHeadings(headspeak, sdate):
	# check and strip the first two headings in as much as they are there
	ih = 0
	ih = StripDebateHeading('Initial', ih, headspeak)

	# House of Lords
	ih = StripDebateHeading('house of lords(?i)', ih, headspeak, True)

	# Thursday, 18th December 2003.
	mdateheading = re.match('(?:<stamp aname="[^"]*"/>)*([\w\s\d,]*)\.', headspeak[ih][0])
	if not mdateheading or (sdate != mx.DateTime.DateTimeFrom(mdateheading.group(1)).date) or headspeak[ih][2]:
		print headspeak[ih]
		#raise ContextException('non-conforming date heading')  # recoverable?
	else:
		ih = ih + 1

	if re.match("THE QUEEN(?:'|&....;)S SPEECH", headspeak[ih][0]):
		print headspeak[ih][0]
		print "QUEENS SPEECH"
		# don't advance, because this is the heading (works for 2005-05-17)

	elif re.match("Parliament", headspeak[ih][0]):
		print "parliamentparliament"
		# don't advance; this is a title (works for 2005-05-11)

	else:
		# The House met at eleven of the clock (Prayers having been read earlier at the Judicial Sitting by the Lord Bishop of St Albans): The CHAIRMAN OF COMMITTEES on the Woolsack.
		gstarttime = re.match('(?:<stamp aname="[^"]*"/>)*(?:reassembling.*?recess, )?the house (?:met|resumed)(?: for Judicial Business)? at ([^(]*)(?i)', headspeak[ih][0])
		if (not gstarttime) or headspeak[ih][2]:
			print "headspeakheadspeakih", headspeak[ih][0]
			raise ContextException('non-conforming "house met at" heading ', fragment=headspeak[ih][0])
		ih = ih + 1

		# Prayers&#151;Read by the Lord Bishop of Southwell.
		ih = StripDebateHeading('prayers(?i)', ih, headspeak, True)



	# find the url, colnum and time stamps that occur before anything else in the unspoken text
	stampurl = StampUrl(sdate)

	# set the time from the wording 'house met at' thing.
	for j in range(0, ih):
		stampurl.UpdateStampUrl(headspeak[j][1])

	if (not stampurl.stamp) or (not stampurl.pageurl):
		raise Exception, ' missing stamp url at beginning of file '
	return (ih, stampurl)



# Handle normal type heading
def LordsHeadingPart(headingtxt, stampurl):
	bmajorheading = False

	headingtxtfx = FixHTMLEntities(headingtxt)
	qb = qspeech('nospeaker="true"', headingtxtfx, stampurl)
	if bmajorheading:
		qb.typ = 'major-heading'
	else:
		qb.typ = 'minor-heading'

	# headings become one unmarked paragraph of text
	qb.stext = [ headingtxtfx ]
	return qb


# this function is taken from debdivisionsections
def SubsPWtextsetS(st):
        return st # this needs tidying up
        if re.search('pwmotiontext="yes"', st) or not re.match('<p', st):
                return st
        return re.sub('<p(.*?)>', '<p\\1 pwmotiontext="yes">', st)

# this function is taken from debdivisionsections
# to be inlined
def SubsPWtextset(stext):
	res = map(SubsPWtextsetS, stext)
	return res

#	<p>On Question, Whether the said amendment (No. 2) shall be agreed to?</p>
#reqput = re.compile('%s|%s|%s|%s|%s(?i)' % (regqput, regqputt, regitbe, regitbepq1, regitbepq))
resaidamend =  re.compile("<p[^>]*>On Question, (?:[Ww]hether|That) (?:the said amendment|the amendment|the House|Clause|Amendment|the Bill|the said [Mm]otion|Lord|the manuscript|the Motion)")

#	<p>On Question, Whether the said amendment (No. 2) shall be agreed to?</p>
#	<p>Their Lordships divided: Contents, 133; Not-Contents, 118.</p>
#housedivtxt = "The (?:House|Committee) (?:(?:having )?divided|proceeded to a Division)"
relorddiv = re.compile('<p[^>]*>(?:\*\s*)?Their Lordships divided: Contents,? (\d+) ?; Not-Contents,? (\d+)\.?</p>$')
def GrabLordDivisionProced(qbp, qbd):
	if not re.match("speech|motion", qbp.typ) or len(qbp.stext) < 1:
		print qbp.stext
		raise Exception, "previous to division not speech"

	hdg = relorddiv.match(qbp.stext[-1])
	if not hdg:
		print qbp.stext[-1]
		raise ContextException("no lordships divided before division", stamp=qbp.sstampurl)

	# if previous thing is already a no-speaker, we don't need to break it out
	# (the coding on the question put is complex and multilined)
	if re.search('nospeaker="true"', qbp.speaker):
		qbp.stext = SubsPWtextset(qbp.stext)
		return None

	# look back at previous paragraphs and skim off a part of what's there
	# to make a non-spoken bit reporting on the division.
	iskim = 1
	if not resaidamend.match(qbp.stext[-2]):
		print qbp.stext[-2]
		raise ContextException("no on said amendment", stamp=qbp.sstampurl, fragment=qbp.stext[-2])
	iskim = 2

	# copy the two lines into a non-speaking paragraph.
	qbdp = qspeech('nospeaker="true"', "", qbp.sstampurl)
	qbdp.typ = 'speech'
	qbdp.stext = SubsPWtextset(qbp.stext[-iskim:])

	# trim back the given one by two lines
	qbp.stext = qbp.stext[:-iskim]

	return qbdp



def MatchPWmotionStuff(qb, ispeechstartp1):
	qpara = qb.stext[ispeechstartp1]

	if re.match('<p>(?:\[|<i>)*(?:Amendments?|Motion),? .{0,60}?by leave,? withdrawn\.?(?:\]|</i>)*</p>', qpara):
		return "withdrawn"

	#[<i>Amendments Nos. 131 and 132 not moved.</i>]</p>
	notmovedMatch = re.match('<p[^>]*>(?:\[|<i>)+Amendments? .{0,80}?(not moved|had been withdrawn from the Marshalled List|had been retabled as(?:Nos?\.|[^<\.\]]){0,60})(?:\.|</i>|\])+</p>', qpara)
	if notmovedMatch:
		return "notmoved"
	if re.match('<p>\[(?:<i>)?The Sitting was suspended .{0,60}?(?:</i>)?\](?:</i>)?</p>', qpara):
		return "suspended"
	if re.match('<p>\[(?:<i>)?The House observed.{0,60}?(\]|\.|</i>)+</p>', qpara):
		return "misc"
	if re.match('<p>\[(?:<i>)?The page and line refer(?:ences are)? to .{0,160}?</p>', qpara):
		return "misc"


	if re.match('<p>.{0,10}?(?:Amendment.{0,50}?|by leave, )withdrawn', qpara):
		raise ContextException("Marginal withdrawn (fragment looks like it might be a withdrawn amendment, \nbut earlier regexp didn't pick it up)", stamp=qb.sstampurl, fragment=qpara)
	if re.match('<p>\s*\[<i>', qpara):
		raise ContextException("Marginal notmoved (fragment looks like it might be an amendment not moved, \nbut an earlier regexp didn't pick it up)", stamp=qb.sstampurl, fragment=qpara)

	if re.match('<p>(?:Moved.? accordingly,? and,? )?(?:[Oo]n [Qq]uestion,? )?(?:original )?(?:Motion|[Aa]mendment)s?(?: No\. \d+| [A-Z])?(?:, as amended)?,? agreed to(?:\.|&mdash;)+</p>', qpara):
		return "agreedto"
	clauseAgreedMatch = re.match('<p>(?:(?:Clause|Schedule)s? \d+[A-Z]*(?:, \d+[A-Z]*)?(?: (?:and|to) \d+[A-Z]*)?|Title|Motion)(?:, as amended,?)? ((?:dis)?agreed to|negatived)\.</p>', qpara)
	if clauseAgreedMatch:
		return clauseAgreedMatch.group(1) == "agreed to" and "agreedto" or "negatived"
	clauseResolvedMatch = re.match('<p>Resolved in the (negative|affirmative),? and (?:Motion|amendment|Clause \d+|Amendment .{5,60}?)(?:, as amended,)? (?:dis)?agreed to accordingly(?:\.</p>|;)', qpara)
	if clauseResolvedMatch:
		return clauseResolvedMatch.group(1) == "negative" and "disagreedto" or "agreedto"
	if re.match('<p>Remaining clauses? (?:and schedules? )?agreed to\.</p>', qpara):
		return "agreedto"
	if re.match('<p>(?:On Question, )(?:Commons )?Amendments? .{0,60} agreed to\.</p>', qpara):
		return "agreedto"
	if re.match('<p>On Motion, Question agreed to\.</p>', qpara):
		return "agreedto"
	if re.match('<p>Schedule agreed to\.</p>', qpara):
		return "agreedto"

	if re.match('<p>Moved, That the .{0,60}? be agreed to\.', qpara):
		return "considered"
	if re.match('<p>On Question, Whether .{0,60}? be agreed to\.', qpara):
		return "considered"

	if re.match('<p>(?:The )?Bill (?:was )?returned (?:earlier )?from the Commons .{0,260}?\.</p>', qpara):
		return "bill"
	if re.match('<p>The Commons (?:do not insist on .{0,160}? but propose|have made the following consequential|(?:dis)?agree (?:to|with)) .{0,260}?(?:\.|&mdash;)+</p>', qpara):
		return "bill"

	if re.match('<p[^>]*>House adjourned at .{0,60}?</p>', qpara):
		return "adjourned"
	if re.match('<p>(?:House|Second [Rr]eading debate|(?:Further )?[Cc]onsideration of amendments on Report) resumed[\.:]', qpara):
		return "resumed"

	if re.match('<p>\*?Their Lordships divided:', qpara):
		return "divided"

	# this is the tag that can be used to give better titles on the motion text.
	if re.match('<p>(?:Clause|Schedule) (?:\d+[A-Z]* )?\[(?:<i>)?.*?(?:</i>)?\]:</p>', qpara):
		return "considered"
	if re.match('<p>On Question, Whether ', qpara):
		return "considered"


	if re.match('<p>(?:Brought|Returned) from the Commons', qpara):
		return "misc"
	if re.match('<p>House (?:again )?in Committee', qpara):
		return "misc"
	if re.match('<p>\[\s*The (?:deputy )?chairman (?i)', qpara):
		#print "CHAIRMAN thing:", qpara
		return "misc"
	if re.match('<p>(?:Bill )?[Rr]ead a third time', qpara):
		return "bill"
	if re.match('<p>An amendment \(privilege\) made\.', qpara):
		return "misc"
	if re.match('<p>Report received\.', qpara):
		return "misc"

	if re.match('<p>Report received\.', qpara):
		return "misc"

	if re.match('<p>:TITLE3:', qpara):
		return "title"

	if re.match("<p>.{0,20}?The noble[^:]{0,60}? said:", qpara):
		print "Unexpected Noble Lord Said; are we missing the start of his speech where he moves the amendment?"
		raise ContextException("unexpected Noble Lord Said", stamp=qb.sstampurl, fragment=qpara)

	if re.match('<p>.{0,60}agreed to(?:\.| accordingly)', qpara):
		print "**********Marginal agreedto", qpara
		raise ContextException("Marginal agreed to", stamp=qb.sstampurl, fragment=qpara)

	return None

def MatchKnownAsPWmotionStuff(qb, ispeechstartp1):
	res = MatchPWmotionStuff(qb, ispeechstartp1)
	if res:
		return res
	qpara = qb.stext[ispeechstartp1]
	if re.match("<p>My Lords", qpara):
		raise ContextException("My Lords in known amendment text", stamp=qb.sstampurl, fragment=qpara)

	if re.match("<p>.{0,60}? Act,? .{0,60}?</p>", qpara):
		return "act"
	if re.match("<p[^>]*>\([d\w]+\) ", qpara):
		return "lines"
	if re.match("<p[^>]*>\( \) ", qpara):
		return "lines"

	if re.match("<p[^>]*>Sections? .{0,30}?</p>", qpara):
		return "lines"
	if re.match("<p[^>]*>(?:Schedule \S+?|The Schedule)(?:, paragraph.{0,60}?)?</p>", qpara):
		return "lines"

	if re.match("<p[^>]*>\d+[A-Z]? ", qpara):
		return "lines"
	if re.match("<p[^>]*>Page \d+, line \d+, ", qpara):
		return "lines"
	if re.match("<p[^>]*>&quot;", qpara):
		return "quot"
	if re.match("<p>[a-z]", qpara): # starting with lower case letter, some kind of continuation
		return "quot"
	if re.match("<p>A message was brought from the Commons", qpara):
		return "message"

	if re.match("<p>The noble .{0,30}?(?:Lord|Baroness|Earl|Viscount) said", qpara):
		print "*****", qpara
		raise ContextException("unexpected weak Noble Lord Said", stamp=qb.sstampurl, fragment=qpara)
	if re.match("<p>The .{5,40}? \([^)]+\):", qpara):
		raise ContextException("unexpected person with position Said", stamp=qb.sstampurl, fragment=qpara)
	if re.match("<p>(?:Lord|Baroness|Earl|Viscount) [\w\s].{5,40}?:", qpara):
		raise ContextException("unexpected person Said, (missing <b>?)", stamp=qb.sstampurl, fragment=qpara)
	if re.match("<p>(?:Lord|Baroness|Earl|Viscount) [\w\s].{5,40}? moved ", qpara):
		raise ContextException("unexpected person moved, (missing <b>?)", stamp=qb.sstampurl, fragment=qpara)

	return None


def SearchForNobleLordSaid(qb, pwmotionsig):
	for i in range(len(qb.stext)):
		rens = re.match("(<p>The (?:noble(?: and learned)?(?: and gallant)? (?:Lord|Baroness|Earl|Viscount|Countess)|right reverend Prelate|most reverend Primate) said:\s*)", qb.stext[i])
		if rens:
			qb.stext[i] = "<p>" +  qb.stext[i][rens.end(1):] # remove "the noble lord said"
			return i
		assert not re.match("the\s*noble(?i)", qb.stext[i])
		qb.stext[i] = re.sub('^<p(.*?)>', '<p\\1 pwmotiontext="%s">' % pwmotionsig, qb.stext[i])
	return len(qb.stext)


# separate out the making of motions and my lords speeches
# the position of a colon gives it away
# returns a pre and post speech accounting for unspoken junk before and after a block of spoken stuff
def FilterLordsSpeech(qb):

	# pull in the normal filtering that gets done on debate speeches
	# does the paragraph indents and tables.  Maybe should be inlined for lords
	FilterDebateSpeech(qb)

	# the colon attr is blank or has a : depending on what was there after the name that was matched
	ispeechstartp1 = 0 # plus 1

	# no colonattr or colon, must be making a speech
	recol = re.search('colon="(:?)"', qb.speaker)
	bSpeakerExists = not re.match('nospeaker="true"', qb.speaker)
	if bSpeakerExists and (not recol or recol.group(1)):
		# text of this kind at the begining should not be spoken
		if re.search("<p>(?:moved|asked) (?i)", qb.stext[0]):
			print qb.speaker
			print qb.stext[0]
			raise ContextException("has moved amendment after colon (try taking : out)", stamp=qb.sstampurl)
		ispeechstartp1 = 1  # 0th paragraph is speech text

	res = [ ] # output list
	preparagraphtype = ""
	if bSpeakerExists and (ispeechstartp1 == 0):
		if re.match("<p>asked Her Majesty's Government|<p>asked the|<p>&mdash;Took the Oath", qb.stext[0]):
			preparagraphtype = "asked"
			qb.stext[0] = re.sub('^<p(.*?)>', '<p\\1 pwmotiontext="%s">' % preparagraphtype, qb.stext[0])
			ispeechstartp1 = 1

			# ensure that the noble lord said doesn't say an amendment withdrawn
			assert not re.match("the\s*noble(?i)", qb.stext[ispeechstartp1])
			assert not MatchPWmotionStuff(qb, ispeechstartp1)
			# if we get "noble lord asked:" after this, insert the words "rose to ask" into the patched text

		elif re.match("<p>rose to (?:ask|call|draw attention|consider)", qb.stext[0]):
			preparagraphtype = "asked"
			ispeechstartp1 = SearchForNobleLordSaid(qb, preparagraphtype)
			if ispeechstartp1 not in [1, 2]:
				print "Noble Lord Said on ", ispeechstartp1, "paragraph"
				raise ContextException("Noble Lord Said missing in second paragraph", stamp=qb.sstampurl)

			# ensure that the noble lord said doesn't say an amendment withdrawn
			assert not MatchPWmotionStuff(qb, ispeechstartp1)

		# identify a writ of summons (single line)
		elif re.match("<p>(?:[\s,]*having received a [Ww]rit of [Ss]ummons .*?)?[Tt]ook the [Oo]ath\.</p>$", qb.stext[0]):
			assert len(qb.stext) == 1
			qb.stext[0] = re.sub('^<p>', '<p pwmotiontext="summons">', qb.stext[0])  # cludgy; already have the <p>-tag embedded in the string
			res.append(qb)
			return res  # bail out

		elif re.match("<p>&mdash;Took the Oath", qb.stext[0]):
			assert False

		# identify a moved amendment
		elif re.match("<p>moved,? |<p>Amendments? |<p>had given notice|<p>rose to move|<p>had given his intention", qb.stext[0]):

			# find where the speech begins, and strip out "The noble lord said:"
			preparagraphtype = "moved"
			ispeechstartp1 = SearchForNobleLordSaid(qb, preparagraphtype)

			# everything up to this point is non-speech
			assert ispeechstartp1 > 0
			qbprev = qspeech(qb.speaker, "", qb.sstampurl)
			qbprev.typ = 'speech'
			qbprev.stext = qb.stext[:ispeechstartp1]

			res.append(qbprev)
			if ispeechstartp1 == len(qb.stext):
				return res

			# upgrade the spoken part
			qb.speaker = string.replace(qb.speaker, 'colon=""', 'colon=":"')
			del qb.stext[:ispeechstartp1]
			assert qb.stext
			ispeechstartp1 = 1 # the spoken text must reach at least here (after the line, "The noble lord said:")

		# error, no moved amendment found
		else:
			print qb.stext
			print "no moved amendment; is a colon missing after the name?"
			raise ContextException("missing moved amendment", stamp=qb.sstampurl)

	# advance to place where non-speeches happen
	if ispeechstartp1 > len(qb.stext):
		print "ispeechstartp1 problem; speeches running through", ispeechstartp1, len(qb.stext)
		print qb.stext
		raise ContextException("end of speech boundary unclear running through; need to separate paragraphs?", stamp=qb.sstampurl)


	# a common end of speech is to withdraw an amendment
	# we go through paragraphs until we match that or some other motion text type statement
	sAmendmentStatement = None
	while bSpeakerExists and (ispeechstartp1 < len(qb.stext)):
		sAmendmentStatement = MatchPWmotionStuff(qb, ispeechstartp1)
		if sAmendmentStatement:
			break

		ispeechstartp1 += 1

	# there are no further lines after the widthdrawal
	if ispeechstartp1 == len(qb.stext):
		assert not sAmendmentStatement
		res.append(qb)
		return res

	# do the further lines after withdrawal
	assert (not bSpeakerExists) or sAmendmentStatement

	# splice off the unspoken text running off from the amendment statements
	if ispeechstartp1 != 0:
		qbunspo = qspeech('nospeaker="true"', "", qb.sstampurl)
		qbunspo.typ = 'speech'
		qbunspo.stext = qb.stext[ispeechstartp1:]
		del qb.stext[ispeechstartp1:]
		res.append(qb)
		res.append(qbunspo)
	else:
		res.append(qb)
		qbunspo = qb

	# check that once we begin pwmotion amendment statements, all statements are of this type
	for i in range(len(qbunspo.stext)):
		sAmendmentStatement = MatchKnownAsPWmotionStuff(qbunspo, i)
		if not sAmendmentStatement:
			print "UNRECOGNIZED-MOTION-TEXT%s: %s" % (bSpeakerExists and " " or "(*)", qbunspo.stext[i])
			sAmendmentStatement = "unrecognized"
		qbunspo.stext[i] = re.sub('^<p(.*?)>', '<p\\1 pwmotiontext="%s">' % sAmendmentStatement, qbunspo.stext[i])

	return res


################
# main function
################
def LordsFilterSections(text, sdate):

	# deal with one exceptional case of indenting
	if sdate == "2005-10-26":
		l = len(text)
		text = re.sub("<ul><ul>(<ul>)?", "<ul>", text)
		text = re.sub("</ul></ul>(</ul>)?", "</ul>", text)

		# regsection1 = '<h\d><center>.*?\s*</center></h\d>' in splitheadingsspeakers.py
		print "Duplicate <ul>s removed and <center> sorted on %s which shortened text by %d" % (sdate, l - len(text))


	# split into list of triples of (heading, pre-first speech text, [ (speaker, text) ])
	headspeak = SplitHeadingsSpeakers(text)


	# break down into lists of headings and lists of speeches
	(ih, stampurl) = StripLordsDebateHeadings(headspeak, sdate)
	if ih == None:
		return

	# loop through each detected heading and the detected partitioning of speeches which follow.
	# this is a flat output of qspeeches, some encoding headings, and some divisions.
	# see the typ variable for the type.
	flatb = [ ]

	for sht in headspeak[ih:]:
		# triplet of ( heading, unspokentext, [(speaker, text)] )
		headingtxt = stampurl.UpdateStampUrl(string.strip(sht[0]))  # we're getting stamps inside the headings sometimes
		unspoketxt = sht[1]
		speechestxt = sht[2]

		# the heading detection, as a division or a heading speech object
		# detect division headings
		gdiv = re.match('Division No. (\d+)', headingtxt)

		# heading type
		if not gdiv:
			qbh = LordsHeadingPart(headingtxt, stampurl)
			flatb.append(qbh)

		# division type
		else:
			(unspoketxt, qbd) = LordsDivisionParsingPart(string.atoi(gdiv.group(1)), unspoketxt, stampurl, sdate)

			# grab some division text off the back end of the previous speech
			# and wrap into a new no-speaker speech
			qbdp = GrabLordDivisionProced(flatb[-1], qbd)
			if qbdp:
				flatb.append(qbdp)
			flatb.append(qbd)

		# continue and output unaccounted for unspoken text occuring after a
		# division, or after a heading
		if (not re.match('(?:<[^>]*>|\s)*$', unspoketxt)):
			qb = qspeech('nospeaker="true"', unspoketxt, stampurl)
			qb.typ = 'speech'
			flatb.extend(FilterLordsSpeech(qb))

		# there is no text; update from stamps if there are any
		else:
			stampurl.UpdateStampUrl(unspoketxt)

		# go through each of the speeches in a block and put it into our batch of speeches
		for ss in speechestxt:
			qb = qspeech(ss[0], ss[1], stampurl)
			qb.typ = 'speech'
			flatb.extend(FilterLordsSpeech(qb))


	# we now have everything flattened out in a series of speeches
	return flatb


