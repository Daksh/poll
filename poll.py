# Copyright 2007 World Wide Workshop Foundation
# Copyright 2007 Collabora Ltd
# Copyright 2008 Morgan Collett
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
#
# If you find this activity useful or end up using parts of it in one of
# your own creations we would love to hear from you at
# info@WorldWideWorkshop.org !
#

import os
import cPickle
import gtk
import hippo
import pango
import locale
import logging
from datetime import date
from gettext import gettext as _
import telepathy
import telepathy.client
from dbus import Interface
from dbus.service import method, signal
from dbus.gobject_service import ExportedGObject
from sugar.presence.tubeconn import TubeConnection

try:
    from hashlib import sha1
except ImportError:
    # Python < 2.5
    from sha import new as sha1

from sugar.activity import activity
from sugar.graphics import style
try:
    from sugar.graphics.alert import NotifyAlert
except:
    pass  # FIXME remove this once compatibility with Trial 3 not required
from sugar.presence import presenceservice
from abiword import Canvas as AbiCanvas
from i18n import LanguageComboBox

SERVICE = "org.worldwideworkshop.olpc.PollBuilder"
IFACE = SERVICE
PATH = "/org/worldwideworkshop/olpc/PollBuilder"

# Theme definitions - colors
LIGHT_GREEN = '#66CC00'
DARK_GREEN = '#027F01'
PINK = '#FF0198'
YELLOW = '#FFFF00'
GRAY = '#ACACAC'
LIGHT_GRAY = '#E2E2E3'
RED = '#FF0000'

COLOR_FG_BUTTONS = (
    (gtk.STATE_NORMAL,"#CCFF99"),
    (gtk.STATE_ACTIVE,"#CCFF99"),
    (gtk.STATE_PRELIGHT,"#CCFF99"),
    (gtk.STATE_SELECTED,"#CCFF99"),
    (gtk.STATE_INSENSITIVE,"#CCFF99"),
    )
COLOR_BG_BUTTONS = (
    (gtk.STATE_NORMAL,"#027F01"),
    (gtk.STATE_ACTIVE,"#014D01"),
    (gtk.STATE_PRELIGHT,"#016D01"),
    (gtk.STATE_SELECTED,"#027F01"),
    (gtk.STATE_INSENSITIVE,"#027F01"),
    )
COLOR_BG_RADIOBUTTONS = (
    (gtk.STATE_NORMAL,LIGHT_GRAY),
    (gtk.STATE_ACTIVE,LIGHT_GRAY),
    (gtk.STATE_PRELIGHT,LIGHT_GRAY),
    (gtk.STATE_SELECTED,LIGHT_GRAY),
    (gtk.STATE_INSENSITIVE,LIGHT_GRAY),
    )
COLOR_FG_RADIOBUTTONS = (
    (gtk.STATE_NORMAL,DARK_GREEN),
    (gtk.STATE_ACTIVE,DARK_GREEN),
    (gtk.STATE_PRELIGHT,DARK_GREEN),
    (gtk.STATE_SELECTED,DARK_GREEN),
    (gtk.STATE_INSENSITIVE,DARK_GREEN),
    )

GRAPH_WIDTH = gtk.gdk.screen_width() / 3
GRAPH_TEXT_WIDTH = GRAPH_WIDTH / 9
RADIO_SIZE = 24

def theme_button(btn, w=-1, h=-1, highlight=False):
    """Apply colors to gtk Buttons
    
    btn is the button
    w and h are optional width and height for resizing the button
    highlight is a boolean to override the theme and apply a
        different color to show "you are here".

    returns the modified button.
    """
    for state, color in COLOR_BG_BUTTONS:
        if highlight:
            btn.modify_bg(state, gtk.gdk.color_parse("#CCFF99"))
        else:
            btn.modify_bg(state, gtk.gdk.color_parse(color))
    c = btn.get_child()
    if c is not None:
        for state, color in COLOR_FG_BUTTONS:
            if highlight:
                c.modify_fg(state, gtk.gdk.color_parse(DARK_GREEN))
            else:
                c.modify_fg(state, gtk.gdk.color_parse(color))
    else:
        for state, color in COLOR_FG_BUTTONS:
            btn.modify_fg(state, gtk.gdk.color_parse(color))
    if w>0 or h>0:
        btn.set_size_request(w, h)
    return btn

def theme_radiobutton(btn):
    """Apply colors and font to gtk RadioButtons
    
    btn -- gtk RadioButton

    returns the modified button.
    """
    for state, color in COLOR_BG_RADIOBUTTONS:
        btn.modify_bg(state, gtk.gdk.color_parse(color))
    c = btn.get_child()
    if c is not None:
        for state, color in COLOR_FG_RADIOBUTTONS:
            c.modify_fg(state, gtk.gdk.color_parse(color))
    else:
        for state, color in COLOR_FG_RADIOBUTTONS:
            btn.modify_fg(state, gtk.gdk.color_parse(color))
    return btn


class PollBuilder(activity.Activity):
    """Sugar activity for polls

    Poll implements a simple tool that allows children to express
    their opinions on a given topic by selecting one of five
    answer choices and submitting a vote. The results are tallied
    by total number of votes and percentage of total votes cast.
    
    A future version of this activity will be networked over the
    OLPC mesh to allow sharing of the poll.
    
    """
    def __init__(self, handle):
        activity.Activity.__init__(self, handle)

        self._logger = logging.getLogger('poll-activity')
        self._logger.debug('Starting Poll activity')

        # get the Presence Service
        self.pservice = presenceservice.get_instance()
        self.initiating = False
        
        # Buddy object for you
        owner = self.pservice.get_owner()
        self.owner = owner
        self.nick = owner.props.nick
        self.nick_sha1 = sha1(self.nick).hexdigest()

        self._basepath = activity.get_bundle_path()
        os.chdir(self._basepath)  # required for i18n.py to work

        # setup example poll
        self._polls = set()
        # Removed default polls since it creates too much noise
        # when shared with many on the mesh
        #self._make_default_poll()
        self._has_voted = False
        self._previewing = False
        self._current_view = None  # so we can switch back

        # Lesson plan widget
        self._lessonplan_widget = None

        toolbox = activity.ActivityToolbox(self)
        self.set_toolbox(toolbox)
        toolbox.show()

        # Show poll screen
        # Setup screen
        self._root = hippo.CanvasBox(orientation = hippo.ORIENTATION_VERTICAL)
        canvas = hippo.Canvas()
        canvas.set_root(self._root)
        self.set_canvas(canvas)
        self.show_all()

        self.set_root(self._select_canvas())

        self.poll_session = None  # PollSession
        self.connect('shared', self._shared_cb)
        self.connect('joined', self._joined_cb)

    def set_root(self, hippo_widget):
        self._root.clear()
        self._root.append(hippo_widget, hippo.PACK_EXPAND)

    def read_file(self, file_path):
        """Implement reading from journal
        
        This is called within sugar.activity.Activity code
        which provides file_path.
        """
        self._logger.debug('Reading file from datastore via Journal: %s' %
                           file_path)
        self._polls = set()
        f = open(file_path, 'r')
        num_polls = cPickle.load(f)
        for p in range(num_polls):
            title = cPickle.load(f)
            author = cPickle.load(f)
            active = cPickle.load(f)
            createdate_i = cPickle.load(f)
            maxvoters = cPickle.load(f)
            question = cPickle.load(f)
            number_of_options = cPickle.load(f)
            options = cPickle.load(f)
            data = cPickle.load(f)
            votes = cPickle.load(f)
            poll = Poll(self, title, author, active, 
                        date.fromordinal(int(createdate_i)),
                        maxvoters, question, number_of_options, options,
                        data, votes)
            self._polls.add(poll)
        f.close()

    def write_file(self, file_path):
        """Implement writing to the journal

        This is called within sugar.activity.Activity code
        which provides the file_path.
        """
        s = cPickle.dumps(len(self._polls))
        for poll in self._polls:
            s += poll.dump()
        f = open(file_path, 'w')
        f.write(s)
        f.close()

    def alert(self, title, text=None):
        """Show an alert above the activity."""
        # FIXME: remove try/except once compatibility with Trial 3 is
        #        no longer required
        try:
            alert = NotifyAlert(timeout=10)
        except NameError:
            return
        alert.props.title = title
        alert.props.msg = text
        self.add_alert(alert)
        alert.connect('response', self._alert_cancel_cb)
        alert.show()

    def _alert_cancel_cb(self, alert, response_id):
        """Callback for alert events"""
        self.remove_alert(alert)

    def _poll_canvas(self):
        """Show the poll canvas where children vote on an existing poll."""
        self._current_view = 'poll'
        canvasbox = self._canvas_root()

        # pollbuilderbox is centered within canvasbox
        pollbuilderbox = self._canvas_pollbuilder_box()
        canvasbox.append(pollbuilderbox, hippo.PACK_EXPAND)

        pollbuilderbox.append(self._canvas_topbox())

        mainbox = self._canvas_mainbox()
        pollbuilderbox.append(mainbox, hippo.PACK_EXPAND)

        if not self._previewing:
            mainbox.append(self._text_mainbox(_('VOTE!')))
        else:
            mainbox.append(self._text_mainbox(_('Poll Preview')))

        poll_details_box = hippo.CanvasBox(spacing=8,
            background_color=style.COLOR_WHITE.get_int(),
            border=4,
            border_color=style.Color(PINK).get_int(),
            padding=20,
            orientation=hippo.ORIENTATION_VERTICAL)
        mainbox.append(poll_details_box, hippo.PACK_EXPAND)
        self.poll_details_box = poll_details_box

        self.current_vote = None
        self.draw_poll_details_box()

        button_box = self._canvas_buttonbox()
        mainbox.append(button_box, hippo.PACK_END)

        return canvasbox

    def _select_canvas(self):
        """Show the select canvas where children choose an existing poll."""
        self._current_view = 'select'
        canvasbox = self._canvas_root()

        # pollbuilderbox is centered within canvasbox
        pollbuilderbox = self._canvas_pollbuilder_box()
        canvasbox.append(pollbuilderbox, hippo.PACK_EXPAND)

        pollbuilderbox.append(self._canvas_topbox())

        mainbox = self._canvas_mainbox()
        pollbuilderbox.append(mainbox, hippo.PACK_EXPAND)

        mainbox.append(self._text_mainbox(_('Choose a Poll')))

        poll_details_box = hippo.CanvasBox(spacing=8,
            background_color=style.COLOR_WHITE.get_int(),
            border=4,
            border_color=style.Color(PINK).get_int(),  # XXXX
            padding=20,
            orientation=hippo.ORIENTATION_VERTICAL)
        mainbox.append(poll_details_box, hippo.PACK_EXPAND)

        # add scroll window
        scrolledwindow = hippo.CanvasScrollbars()
        scrolledwindow.set_policy(
            hippo.ORIENTATION_HORIZONTAL, hippo.SCROLLBAR_NEVER)

        poll_selector_box = hippo.CanvasBox(
            background_color=style.COLOR_WHITE.get_int(),
            orientation=hippo.ORIENTATION_VERTICAL)
        scrolledwindow.set_root(poll_selector_box)
        poll_details_box.append(scrolledwindow,
                                hippo.PACK_EXPAND)

        row_number = 0
        for poll in self._polls:
            sha = poll.sha
            if row_number % 2:
                row_bgcolor=style.COLOR_WHITE.get_int()
            else:
                row_bgcolor=style.COLOR_SELECTION_GREY.get_int()
            row_number += 1
            poll_row = hippo.CanvasBox(
                padding_top=4, padding_bottom=4,
                background_color=row_bgcolor,
                orientation=hippo.ORIENTATION_HORIZONTAL)
            poll_selector_box.append(poll_row)

            sized_box = hippo.CanvasBox(
                box_width=600,
                orientation=hippo.ORIENTATION_HORIZONTAL)
            poll_row.append(sized_box)
            title = hippo.CanvasText(
                text=poll.title+' ('+poll.author+')',
                xalign=hippo.ALIGNMENT_START,
                color=style.Color(DARK_GREEN).get_int())
            sized_box.append(title)

            sized_box = hippo.CanvasBox(
                box_width=180,
                orientation=hippo.ORIENTATION_HORIZONTAL)
            poll_row.append(sized_box)
            if poll.active:
                button = gtk.Button(_('VOTE'))
            else:
                button = gtk.Button(_('SEE RESULTS'))
            button.connect('clicked', self._select_poll_button_cb, sha)
            sized_box.append(hippo.CanvasWidget(widget=theme_button(button)))

            sized_box = hippo.CanvasBox(
                box_width=150,
                orientation=hippo.ORIENTATION_HORIZONTAL)
            poll_row.append(sized_box)
            if poll.author == self._pservice.get_owner().props.nick:
                button = gtk.Button(_('DELETE'))
                button.connect('clicked', self._delete_poll_button_cb, sha)
                sized_box.append(hippo.CanvasWidget(widget=theme_button(button)))
            poll_row.append(hippo.CanvasText(
                text=poll.createdate.strftime('%d/%m/%y'),
                color=style.Color(DARK_GREEN).get_int()))

        button_box = self._canvas_buttonbox(button_to_highlight=2)
        mainbox.append(button_box, hippo.PACK_END)

        return canvasbox

    def _lessonplan_canvas(self):
        """Show the select canvas where children choose an existing poll."""
        previous_view = self._current_view
        self._current_view = 'lessonplan'
        canvasbox = self._canvas_root()

        # pollbuilderbox is centered within canvasbox
        pollbuilderbox = self._canvas_pollbuilder_box()
        canvasbox.append(pollbuilderbox, hippo.PACK_EXPAND)

        pollbuilderbox.append(self._canvas_topbox(lesson_return=previous_view))

        mainbox = self._canvas_mainbox()
        pollbuilderbox.append(mainbox, hippo.PACK_EXPAND)

        mainbox.append(self._text_mainbox(_('Lesson Plans')))

        poll_details_box = hippo.CanvasBox(spacing=8,
            background_color=style.COLOR_WHITE.get_int(),
            border=4,
            border_color=style.Color(PINK).get_int(),
            padding=20,
            orientation=hippo.ORIENTATION_VERTICAL)
        mainbox.append(poll_details_box, hippo.PACK_EXPAND)

        lessonplan = LessonPlanWidget(self._basepath)
        self._lessonplan_widget = lessonplan
        poll_details_box.append(hippo.CanvasWidget(widget=lessonplan),
                                hippo.PACK_EXPAND)

        button_box = self._canvas_buttonbox()
        mainbox.append(button_box, hippo.PACK_END)

        return canvasbox

    def _select_poll_button_cb(self, button, sha=None):
        """A VOTE or SEE RESULTS button was clicked."""
        if not sha:
            self._logger.debug('Strange, which button was clicked?')
            return
        self._switch_to_poll(sha)
        self._has_voted = False
        self.set_root(self._poll_canvas())
        self.show_all()

    def _delete_poll_button_cb(self, button, sha=None):
        """A DELETE button was clicked."""
        if not sha:
            self._logger.debug('Strange, which button was clicked?')
            return
        self.delete_poll(sha)
        self.set_root(self._select_canvas())
        self.show_all()

    def delete_poll(self, sha=None, poll=None):
        """Delete a poll, either by passing sha or the actual poll object.

        sha -- string, sha property of the poll
        poll -- Poll
        """
        if poll:
            if self._poll == poll:
                self._make_blank_poll
            self._polls.remove(poll)
        if sha:
            if self._poll.sha == sha:
                self._logger.debug('delete_poll: removing current poll')
                self._make_blank_poll()
            for poll in self._polls.copy():
                if poll.sha == sha:
                    self._polls.remove(poll)
        
    def draw_poll_details_box(self):
        """(Re)draw the poll details box
        
        self.poll_details_box should be already defined on the canvas.
        """
        poll_details_box = self.poll_details_box
        poll_details_box.remove_all()

        votes_total = self._poll.vote_count

        title = hippo.CanvasText(
            text=self._poll.title,
            xalign=hippo.ALIGNMENT_START,
            color=style.Color(DARK_GREEN).get_int())
        title.props.size_mode = 'wrap-word'
        poll_details_box.append(title)
        question = hippo.CanvasText(
            text=self._poll.question,
            xalign=hippo.ALIGNMENT_START,
            color=style.Color(DARK_GREEN).get_int())
        question.props.size_mode = 'wrap-word'
        poll_details_box.append(question)

        group = gtk.RadioButton()  # required for radio button group

        for choice in range(self._poll.number_of_options):
            self._logger.debug(self._poll.options[choice])

            answer_row = hippo.CanvasBox(spacing=8,
                    orientation=hippo.ORIENTATION_HORIZONTAL)

            radio_box = hippo.CanvasBox(
                    box_width = RADIO_SIZE + RADIO_SIZE/2,
                    box_height = RADIO_SIZE,
                    orientation = hippo.ORIENTATION_HORIZONTAL)
            answer_row.append(radio_box)

            if self._poll.active:
                button = gtk.RadioButton(group, '')
                button.connect('toggled', self.vote_choice_radio_button, choice)
                radio_box.append(hippo.CanvasWidget(
                        widget = theme_radiobutton(button)),
                        hippo.PACK_EXPAND)

            answer_row.append(hippo.CanvasText(
                    text = self._poll.options[choice],
                    color = style.Color(DARK_GREEN).get_int(),
                    xalign=hippo.ALIGNMENT_START,
                    size_mode = 'wrap-word'),
                    hippo.PACK_EXPAND)

            if votes_total > 0:
                self._logger.debug(str(self._poll.data[choice] * 1.0 / votes_total))

                graph_box = hippo.CanvasBox(
                        box_width = GRAPH_WIDTH,
                        orientation = hippo.ORIENTATION_HORIZONTAL)
                answer_row.append(graph_box)

                graph_box.append(hippo.CanvasText(
                        text=justify(self._poll.data, choice),
                        xalign=hippo.ALIGNMENT_END,
                        padding_right = 2,
                        color=style.Color(DARK_GREEN).get_int(),
                        box_width = GRAPH_TEXT_WIDTH))


                graph_box.append(hippo.CanvasBox(
                        orientation=hippo.ORIENTATION_HORIZONTAL,
                        background_color=style.Color(PINK).get_int(),
                        box_width = int(float(self._poll.data[choice]) *
                            (GRAPH_WIDTH - GRAPH_TEXT_WIDTH*2) / votes_total)))

                graph_box.append(hippo.CanvasText(
                        text=str(self._poll.data[choice] * 100 / votes_total)+'%',
                        xalign=hippo.ALIGNMENT_START,
                        padding_left = 2,
                        color=style.Color(DARK_GREEN).get_int(),
                        box_width = GRAPH_TEXT_WIDTH))

            poll_details_box.append(answer_row)

        if (self._poll.active and self._has_voted) or\
            not self._poll.active:

            # Line above total
            line_box = hippo.CanvasBox(
                xalign=hippo.ALIGNMENT_END,
                spacing=8,
                box_height=4,
                padding_left = GRAPH_TEXT_WIDTH,
                padding_right = GRAPH_TEXT_WIDTH,
                orientation=hippo.ORIENTATION_HORIZONTAL)
            line = hippo.CanvasBox(
                background_color=style.Color(DARK_GREEN).get_int(),
                box_width = GRAPH_WIDTH - GRAPH_TEXT_WIDTH*2,
                orientation=hippo.ORIENTATION_HORIZONTAL)
            line_box.append(line)
            poll_details_box.append(line_box)

            # total votes
            totals_box = hippo.CanvasBox(
                xalign=hippo.ALIGNMENT_END,
                box_width = GRAPH_WIDTH,
                spacing=8,
                padding_left = GRAPH_TEXT_WIDTH,
                padding_right = GRAPH_TEXT_WIDTH,
                orientation=hippo.ORIENTATION_HORIZONTAL)
            poll_details_box.append(totals_box)

            spacer = hippo.CanvasBox(
                box_width=100, orientation=hippo.ORIENTATION_VERTICAL)

            spacer.append(hippo.CanvasText(
                text=str(votes_total),
                xalign=hippo.ALIGNMENT_END,
                color=style.Color(DARK_GREEN).get_int()))
            totals_box.append(spacer)

            totals_box.append(hippo.CanvasText(
                text=' '+_('votes'),
                xalign=hippo.ALIGNMENT_START,
                color=style.Color(DARK_GREEN).get_int()))
            if votes_total < self._poll.maxvoters:
                totals_box.append(hippo.CanvasText(
                    text=' ('+str(self._poll.maxvoters-votes_total)+
                         ' votes left to collect)',
                    color=style.Color(DARK_GREEN).get_int()))

        # Button area
        if self._poll.active and not self._previewing:
            button_box = hippo.CanvasBox(spacing=8,
                padding = 8,
                orientation=hippo.ORIENTATION_HORIZONTAL)
            button = gtk.Button(_("Vote"))
            button.connect('clicked', self._button_vote_cb)
            button_box.append(hippo.CanvasWidget(widget=theme_button(button)))
            poll_details_box.append(button_box)
        elif self._previewing:
            button_box = hippo.CanvasBox(spacing=8,
                padding = 8,
                orientation=hippo.ORIENTATION_HORIZONTAL)
            button = gtk.Button(_("Edit Poll"))
            button.connect('clicked', self.button_edit_clicked)
            button_box.append(hippo.CanvasWidget(widget=theme_button(button)))
            button = gtk.Button(_("Save Poll"))
            button.connect('clicked', self._button_save_cb)
            button_box.append(hippo.CanvasWidget(widget=theme_button(button)))
            poll_details_box.append(button_box)

    def vote_choice_radio_button(self, widget, data=None):
        """Track which radio button has been selected

        This is connected to the vote choice radio buttons.
        data contains the choice (0 - 4) selected.
        """
        self.current_vote = data

    def _button_vote_cb(self, button):
        """Register a vote

        Take the selected option from self.current_vote
        and increment the poll_data.
        """
        if self.current_vote is not None:
            if self._poll.vote_count >= self._poll.maxvoters:
                self._logger.debug(
                    'Hit the max voters, ignoring this vote.')
                return
            self._logger.debug('Voted '+str(self.current_vote))
            self._has_voted = True
            try:
                self._poll.register_vote(self.current_vote, self.nick_sha1)
            except OverflowError:
                self._logger.debug('Local vote failed: '
                    'maximum votes already registered.')
            except ValueError:
                self._logger.debug('Local vote failed: '
                    'poll closed.')
            self._logger.debug('Results: '+str(self._poll.data))
            self.draw_poll_details_box()

    def button_select_clicked(self, button):
        """Show Choose a Poll canvas"""
        self.set_root(self._select_canvas())
        self.show_all()

    def button_new_clicked(self, button):
        """Show Build a Poll canvas.
        """
        # Reset vote data to 0
        self._make_blank_poll()
        owner = self._pservice.get_owner()
        self._poll.author = owner.props.nick
        self._poll.active = False
        self.set_root(self._build_canvas())
        self.show_all()

    def button_edit_clicked(self, button):
        """Go back from preview to edit"""
        self.set_root(self._build_canvas())
        self.show_all()

    def _build_canvas(self, editing=False, highlight=[]):
        """Show the canvas to set up a new poll.
        
        editing is False to start a new poll, or
        True to edit the current poll

        highlight is a list of strings denoting items failing validation.
        """
        self._current_view = 'build'
        canvasbox = self._canvas_root()

        # pollbuilderbox is centered within canvasbox
        pollbuilderbox = self._canvas_pollbuilder_box()
        canvasbox.append(pollbuilderbox, hippo.PACK_EXPAND)

        pollbuilderbox.append(self._canvas_topbox())

        mainbox = self._canvas_mainbox()
        pollbuilderbox.append(mainbox, hippo.PACK_EXPAND)

        mainbox.append(self._text_mainbox(_('Build a Poll')))

        poll_details_box = hippo.CanvasBox(spacing=8,
            background_color=style.COLOR_WHITE.get_int(),
            border=4,
            border_color=style.Color(PINK).get_int(),
            padding=20,
            orientation=hippo.ORIENTATION_VERTICAL)
        mainbox.append(poll_details_box, hippo.PACK_EXPAND)

        buildbox = hippo.CanvasBox(spacing=8,
            #xalign=hippo.ALIGNMENT_CENTER,
            orientation=hippo.ORIENTATION_VERTICAL)
        poll_details_box.append(buildbox, hippo.PACK_EXPAND)
        
        hbox = hippo.CanvasBox(spacing=8,
            orientation=hippo.ORIENTATION_HORIZONTAL)
        hbox.append(self._text_mainbox(_('Poll Title:'),
                                       warn='title' in highlight))
        entrybox = gtk.Entry()
        entrybox.set_text(self._poll.title)
        entrybox.connect('changed', self._entry_activate_cb, 'title')
        hbox.append(hippo.CanvasWidget(widget=entrybox), hippo.PACK_EXPAND)
        buildbox.append(hbox, hippo.PACK_EXPAND)

        hbox = hippo.CanvasBox(spacing=8,
            orientation=hippo.ORIENTATION_HORIZONTAL)
        hbox.append(self._text_mainbox(_('Question:'),
                                       warn='question' in highlight))
        entrybox = gtk.Entry()
        entrybox.set_text(self._poll.question)
        entrybox.connect('changed', self._entry_activate_cb, 'question')
        hbox.append(hippo.CanvasWidget(widget=entrybox), hippo.PACK_EXPAND)
        buildbox.append(hbox, hippo.PACK_EXPAND)

        hbox = hippo.CanvasBox(spacing=8,
            orientation=hippo.ORIENTATION_HORIZONTAL)
        hbox.append(self._text_mainbox(_('Number of votes to collect:'),
                                       warn='maxvoters' in highlight))
        entrybox = gtk.Entry()
        entrybox.set_text(str(self._poll.maxvoters))
        entrybox.connect('changed', self._entry_activate_cb, 'maxvoters')
        hbox.append(hippo.CanvasWidget(widget=entrybox))
        buildbox.append(hbox)

        for choice in self._poll.options.keys():
            hbox = hippo.CanvasBox(spacing=8,
                orientation=hippo.ORIENTATION_HORIZONTAL)
            hbox.append(self._text_mainbox(_('Answer') + ' ' + str(choice+1) +
                                           ':',
                                           warn=str(choice) in highlight))
            entrybox = gtk.Entry()
            entrybox.set_text(self._poll.options[choice])
            entrybox.connect('changed', self._entry_activate_cb, str(choice))
            hbox.append(hippo.CanvasWidget(widget=entrybox), hippo.PACK_EXPAND)
            buildbox.append(hbox, hippo.PACK_EXPAND)

        # PREVIEW & SAVE buttons
        hbox = hippo.CanvasBox(spacing=8,
            orientation=hippo.ORIENTATION_HORIZONTAL)
        button = gtk.Button(_("Step 1: Preview"))
        button.connect('clicked', self._button_preview_cb)
        hbox.append(hippo.CanvasWidget(widget=theme_button(button)))
        button = gtk.Button(_("Step 2: Save"))
        button.connect('clicked', self._button_save_cb)
        hbox.append(hippo.CanvasWidget(widget=theme_button(button)))
        buildbox.append(hbox)
        
        button_box = self._canvas_buttonbox(button_to_highlight=1)
        mainbox.append(button_box, hippo.PACK_END)

        return canvasbox

    def _button_preview_cb(self, button, data=None):
        """Preview button clicked."""
        # Validate data
        failed_items = self._validate()
        if failed_items:
            self.set_root(self._build_canvas(highlight=failed_items))
            self.show_all()
            return
        # Data OK
        self._poll.active = True  # Show radio buttons
        self._previewing = True
        self.set_root(self._poll_canvas())
        self.show_all()

    def _button_save_cb(self, button, data=None):
        """Save button clicked."""
        # Validate data
        failed_items = self._validate()
        if failed_items:
            self.set_root(self._build_canvas(highlight=failed_items))
            self.show_all()
            return
        # Data OK
        self._previewing = False
        self._poll.active = True
        self._polls.add(self._poll)
        self._poll.broadcast_on_mesh()
        self.set_root(self._poll_canvas())
        self.show_all()

    def _entry_activate_cb(self, entrycontrol, data=None):
        text = entrycontrol.props.text
        if data:
            if text:
                if data=='title':
                    self._poll.title = text
                elif data=='question':
                    self._poll.question = text
                elif data=='maxvoters':
                    try:
                        self._poll.maxvoters = int(text)
                    except ValueError:
                        self._poll.maxvoters = 0  # invalid, will be trapped
                else:
                    self._poll.options[int(data)] = text

    def _make_blank_poll(self):
        """Initialize the poll state."""
        self._poll = Poll(activity=self)
        self.current_vote = None

    def _make_default_poll(self):
        """A hardcoded poll for first time launch."""
        self._poll = Poll(
            activity=self, title=self.nick + ' ' + _('Favorite Color'),
            author=self.nick, active=True,
            question=_('What is your favorite color?'),
            options = {0: _('Green'), 1: _('Red'), 2: _('Blue'),
                3: _('Orange'), 4: _('None of the above')})
        self.current_vote = None
        self._polls.add(self._poll)

    def _validate(self):
        failed_items = []
        if self._poll.title == '':
            failed_items.append('title')
        if self._poll.question == '':
            failed_items.append('question')
        if self._poll.maxvoters == 0:
            failed_items.append('maxvoters')
        if self._poll.options[0] == '':
            failed_items.append('0')
        if self._poll.options[1] == '':
            failed_items.append('1')
        if self._poll.options[3] != '' and self._poll.options[2] == '':
            failed_items.append('2')
        if self._poll.options[4] != '' and self._poll.options[3] == '':
            failed_items.append('3')
        if self._poll.options[2] == '':
            self._poll.number_of_options = 2
        elif self._poll.options[3] == '':
            self._poll.number_of_options = 3
        elif self._poll.options[4] == '':
            self._poll.number_of_options = 4
        else:
            self._poll.number_of_options = 5
        return failed_items
            
    def _get_sha(self):
        """Return a sha1 hash of something about this poll.
        
        Currently we sha1 the poll title and author.
        This is used for the filename of the saved poll.
        It will probably be used for the mesh networking too.
        """
        return self._poll.sha
    
    def _switch_to_poll(self, sha):
        """Set self._poll to the specified poll with sha

        sha -- string
        """
        for poll in self._polls:
            if poll.sha == sha:
                self._poll = poll

    def get_my_polls(self):
        """Return list of Polls for all polls I created."""
        return [poll for poll in self._polls if poll.author==self.nick] 

    def vote_on_poll(self, author, title, choice, votersha):
        """Register a vote on a poll from the mesh.
        
        author -- string
        title -- string
        choice -- integer 0-4
        votersha -- string
          sha1 of the voter nick
        """
        for poll in self._polls:
            if poll.author == author and poll.title == title:
                try:
                    poll.register_vote(choice, votersha)
                    self.alert(_('Vote'),
                               _('Somebody voted on %s') % title)
                except OverflowError:
                    self._logger.debug('Ignored mesh vote %u from %s:'
                        ' poll reached maximum votes.',
                        choice, votersha)
                except ValueError:
                    self._logger.debug('Ignored mesh vote %u from %s:'
                        ' poll closed.',
                        choice, votersha)

    def _canvas_language_select_box(self):
        """CanvasBox definition for lang select box.
        
        Called from _poll_canvas, _select_canvas, _build_canvas
        """
        languageselectbox = hippo.CanvasBox(
            background_color=style.Color(LIGHT_GREEN).get_int(),
            border_top=4, border_left=4,
            border_color=style.Color(YELLOW).get_int(),
            padding_top=12, padding_bottom=12,
            padding_left=100, padding_right=100,
            orientation=hippo.ORIENTATION_VERTICAL)
        button = LanguageComboBox()
        button.install()
        languageselectbox.append(hippo.CanvasWidget(widget=theme_button(button)))
        return languageselectbox

    def _canvas_pollbuilder_box(self):
        """CanvasBox definition for pollbuilderbox.
        
        Called from _poll_canvas, _select_canvas, _build_canvas
        """
        pollbuilderbox = hippo.CanvasBox(
            border=4,
            border_color=style.Color(GRAY).get_int(),
            orientation=hippo.ORIENTATION_VERTICAL)
        return pollbuilderbox

    def _canvas_root(self):
        """CanvasBox definition for main canvas.
        
        Called from _poll_canvas, _select_canvas, _build_canvas
        """
        canvasbox = hippo.CanvasBox(
            background_color=style.COLOR_SELECTION_GREY.get_int(),
            orientation=hippo.ORIENTATION_VERTICAL)
        return canvasbox

    def _canvas_topbox(self, lesson_return=None):
        """Render topbox.

        lesson_return is the view we want to return to from
        lesson plan if the lesson plan button is clicked.
        """
        topbox = hippo.CanvasBox(
            background_color=style.Color(LIGHT_GREEN).get_int(),
            orientation=hippo.ORIENTATION_HORIZONTAL)
        topbox.append(hippo.CanvasWidget(widget=self._logo()))
        languageselectbox = self._canvas_language_select_box()
        topbox.append(languageselectbox, hippo.PACK_EXPAND)
        lessonplanbox = self._canvas_lessonplanbox(lesson_return)
        topbox.append(lessonplanbox, hippo.PACK_EXPAND)
        return topbox

    def _logo(self):
        logoimage = gtk.Image()
        logoimage.set_from_file(os.path.join(
            self._basepath,
            'GameLogoCharacter.png'))
        return logoimage

    def _canvas_lessonplanbox(self, lesson_return=None):
        """Render the lessonplanbox.

        disconnect_lp True does not connect the button.
        """
        lessonplanbox = hippo.CanvasBox(
            background_color=style.Color(LIGHT_GREEN).get_int(),
            border_top=4, border_left=4, border_right=4,
            border_color=style.Color(YELLOW).get_int(),
            padding_top=12, padding_bottom=12,
            padding_left=30, padding_right=30,
            orientation=hippo.ORIENTATION_VERTICAL)
        if lesson_return:
            highlight = True
            button = gtk.Button(_("Close Lessons"))
        else:
            highlight = False
            button = gtk.Button(_("Lesson Plans"))
        if lesson_return:
            button.connect('clicked', self._button_closelessonplan_cb, lesson_return)
        else:
            button.connect('clicked', self._button_lessonplan_cb)
        lessonplanbox.append(hippo.CanvasWidget(widget=theme_button(
            button, highlight=highlight)))
        return lessonplanbox

    def _button_lessonplan_cb(self, button):
        """Lesson Plan button clicked."""
        self._logger.debug('%s -> Lesson Plan' % self._current_view)
        self.set_root(self._lessonplan_canvas())
        self.show_all()

    def _button_closelessonplan_cb(self, button, lesson_return):
        """Lesson Plan button clicked in Lesson Plan view.
        
        Go back to the view we had previously.
        """
        self._logger.debug('Lesson plans -> %s' % lesson_return)
        if lesson_return == 'poll':
            self.set_root(self._poll_canvas())
        elif lesson_return == 'select':
            self.set_root(self._select_canvas())
        elif lesson_return == 'build':
            self.set_root(self._build_canvas())
        self.show_all()
        del self._lessonplan_widget
        self._lessonplan_widget = None

    def _canvas_mainbox(self):
        mainbox = hippo.CanvasBox(spacing=4,
            background_color=style.Color(LIGHT_GREEN).get_int(),
            border=4,
            border_color=style.Color(YELLOW).get_int(),
            padding_top=20, padding_left=40, padding_right=40,
            padding_bottom=20,
            orientation=hippo.ORIENTATION_VERTICAL)
        return mainbox

    def _text_mainbox(self, text, warn=False):
        """Main text style.
        
        warn=True makes the text color RED and appends ???.
        """
        if warn:
            text_color = RED
            text = text + '???'
        else:
            text_color = DARK_GREEN
        return hippo.CanvasText(
            text=text,
            xalign=hippo.ALIGNMENT_START,
            color=style.Color(text_color).get_int())

    def _canvas_buttonbox(self, button_to_highlight=None):
        button_box = hippo.CanvasBox(
            spacing=8,
            padding=8,
            orientation=hippo.ORIENTATION_HORIZONTAL)
        button = gtk.Button(_("Build a Poll"))
        button.connect('clicked', self.button_new_clicked)
        button_box.append(hippo.CanvasWidget(
            widget=theme_button(button,
                               highlight=(button_to_highlight==1))))
        button = gtk.Button(_("Choose a Poll"))
        button.connect('clicked', self.button_select_clicked)
        button_box.append(hippo.CanvasWidget(
            widget=theme_button(button,
                               highlight=(button_to_highlight==2))))
        return button_box

    def _shared_cb(self, activity):
        """Callback for completion of sharing this activity."""
        self._logger.debug('My activity was shared')
        self.initiating = True
        self._sharing_setup()

        self._logger.debug('This is my activity: making a tube...')
        id = self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].OfferDBusTube(
            SERVICE, {})

    def _sharing_setup(self):
        """Setup my Tubes channel.
        
        Called from _shared_cb or _joined_cb.
        """
        if self._shared_activity is None:
            self._logger.error('Failed to share or join activity')
            return

        self.conn = self._shared_activity.telepathy_conn
        self.tubes_chan = self._shared_activity.telepathy_tubes_chan
        self.text_chan = self._shared_activity.telepathy_text_chan

        self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].connect_to_signal(
            'NewTube', self._new_tube_cb)

        self._shared_activity.connect('buddy-joined', self._buddy_joined_cb)
        self._shared_activity.connect('buddy-left', self._buddy_left_cb)

    def _list_tubes_reply_cb(self, tubes):
        for tube_info in tubes:
            self._new_tube_cb(*tube_info)

    def _list_tubes_error_cb(self, e):
        self._logger.error('ListTubes() failed: %s', e)

    def _joined_cb(self, activity):
        """Callback for completion of joining the activity."""
        if not self._shared_activity:
            return

        self._logger.debug('Joined an existing shared activity')
        self.alert(_('Joined'))
        self.initiating = False
        self._sharing_setup()

        self._logger.debug('This is not my activity: waiting for a tube...')
        self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].ListTubes(
            reply_handler=self._list_tubes_reply_cb,
            error_handler=self._list_tubes_error_cb)

    def _new_tube_cb(self, id, initiator, type, service, params, state):
        """Callback for when we have a Tube."""
        self._logger.debug('New tube: ID=%d initator=%d type=%d service=%s '
                     'params=%r state=%d', id, initiator, type, service,
                     params, state)

        if (type == telepathy.TUBE_TYPE_DBUS and
            service == SERVICE):
            if state == telepathy.TUBE_STATE_LOCAL_PENDING:
                self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].AcceptDBusTube(id)

            tube_conn = TubeConnection(self.conn,
                self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES],
                id, group_iface=self.text_chan[telepathy.CHANNEL_INTERFACE_GROUP])
            self.poll_session = PollSession(tube_conn, self.initiating, self._get_buddy, self)

    def _buddy_joined_cb (self, activity, buddy):
        self.alert(buddy.props.nick, _('Joined'))
        self._logger.debug('Buddy %s joined' % buddy.props.nick)

    def _buddy_left_cb (self, activity, buddy):
        self.alert(buddy.props.nick, _('Left'))
        self._logger.debug('Buddy %s left' % buddy.props.nick)

    def _get_buddy(self, cs_handle):
        """Get a Buddy from a channel specific handle."""
        self._logger.debug('Trying to find owner of handle %u...', cs_handle)
        group = self.text_chan[telepathy.CHANNEL_INTERFACE_GROUP]
        my_csh = group.GetSelfHandle()
        self._logger.debug('My handle in that group is %u', my_csh)
        if my_csh == cs_handle:
            handle = self.conn.GetSelfHandle()
            self._logger.debug('CS handle %u belongs to me, %u', cs_handle, handle)
        elif group.GetGroupFlags() & telepathy.CHANNEL_GROUP_FLAG_CHANNEL_SPECIFIC_HANDLES:
            handle = group.GetHandleOwners([cs_handle])[0]
            self._logger.debug('CS handle %u belongs to %u', cs_handle, handle)
        else:
            handle = cs_handle
            self._logger.debug('non-CS handle %u belongs to itself', handle)
            assert handle != 0
        return self.pservice.get_buddy_by_telepathy_handle(
            self.conn.service_name, self.conn.object_path, handle)


class Poll:
    """Represent the data of one poll."""
    def __init__(self, activity=None, title='', author='', active=False,
                 createdate=date.today(), maxvoters=20, question='',
                 number_of_options=5, options=None, data=None, votes=None):
        """Create the Poll."""
        self.activity = activity
        self.title = title
        self.author = author
        self.active = active
        self.createdate = createdate
        self.maxvoters = maxvoters
        self.question = question
        self.number_of_options = number_of_options
        self.options = (options or {0: '', 1: '', 2: '', 3: '', 4: ''})
        self.data = (data or {0:0, 1:0, 2:0, 3:0, 4:0})
        self.votes = (votes or {})
        self._logger = logging.getLogger('poll-activity.Poll')
        self._logger.debug('Creating Poll(%s by %s)' % (title, author))

    def dump(self):
        """Dump a pickled version for the journal"""
        # The attributes may be dbus types. These are not serialisable
        # with pickle at the moment, so convert them to builtin types.
        # Pay special attention to dicts - we need to convert the keys
        # and values too.
        s = cPickle.dumps(str(self.title))
        s += cPickle.dumps(str(self.author))
        s += cPickle.dumps(bool(self.active))
        s += cPickle.dumps(self.createdate.toordinal())
        s += cPickle.dumps(int(self.maxvoters))
        s += cPickle.dumps(str(self.question))
        s += cPickle.dumps(int(self.number_of_options))
        options = {}
        for key in self.options:
            value = self.options[key]
            options[int(key)] = str(value)
        data = {}
        for key in self.data:
            value = self.data[key]
            data[int(key)] = int(value)
        votes = {}
        for key in self.votes:
            value = self.votes[key]
            votes[str(key)] = int(value)
        s += cPickle.dumps(options)
        s += cPickle.dumps(data)
        s += cPickle.dumps(votes)
        return s

    @property
    def vote_count(self):
        """Return the total votes cast."""
        total = 0
        for choice in self.options.keys():
            total += self.data[choice]
        return total

    @property
    def sha(self):
        """Return a sha1 hash of something about this poll.

        Currently we sha1 the poll title and author.
        """
        return sha1(self.title + self.author).hexdigest()

    def register_vote(self, choice, votersha):
        """Register a vote on the poll.

        votersha -- string
          sha1 of the voter nick
        """
        self._logger.debug('In Poll.register_vote')
        if self.active:
            if self.vote_count < self.maxvoters:
                self._logger.debug('About to vote')
                # XXX 27/10/07 Morgan: Allowing multiple votes per XO
                #                      per Shannon's request.
                ## if voter already voted, change their vote:
                #if votersha in self.votes:
                #    self._logger.debug('%s already voted, decrementing their '
                #        'old choice %d' % (votersha, self.votes[votersha]))
                #    self.data[self.votes[votersha]] -= 1
                self.votes[votersha] = choice
                self.data[choice] += 1
                self._logger.debug(
                    'Recording vote %d by %s on %s by %s' %
                    (choice, votersha, self.title, self.author))
                # Close poll:
                if self.vote_count >= self.maxvoters:
                    self.active = False
                    self._logger.debug('Poll hit maxvoters, closing')
                if self.activity.poll_session:
                    # We are shared so we can send the Vote signal if I voted
                    if votersha == self.activity.nick_sha1:
                        self._logger.debug(
                            'Shared, I voted so sending signal')
                        self.activity.poll_session.Vote(
                            self.author, self.title, choice, votersha)
            else:
                raise OverflowError, 'Poll reached maxvoters'
        else:
            raise ValueError, 'Poll closed'

    def broadcast_on_mesh(self):
        if self.activity.poll_session:
            # We are shared so we can broadcast this poll
            self.activity.poll_session.UpdatedPoll(
                self.title, self.author, self.active,
                self.createdate.toordinal(),
                self.maxvoters, self.question, self.number_of_options,
                self.options, self.data, self.votes) 


class PollSession(ExportedGObject):
    """The bit that talks over the TUBES!!!"""

    def __init__(self, tube, is_initiator, get_buddy, activity):
        """Initialise the PollSession.

        tube -- TubeConnection
        is_initiator -- boolean, True = we are sharing, False = we are joining
        get_buddy -- function
        activity -- PollBuilder (sugar.activity.Activity)
        """
        super(PollSession, self).__init__(tube, PATH)
        self._logger = logging.getLogger('poll-activity.PollSession')
        self.tube = tube
        self.is_initiator = is_initiator
        self.entered = False  # Have we set up the tube?
        self._get_buddy = get_buddy  # Converts handle to Buddy object
        self.activity = activity  # PollBuilder
        self.tube.watch_participants(self.participant_change_cb)

    def participant_change_cb(self, added, removed):
        """Callback when tube participants change."""
        self._logger.debug('In participant_change_cb')
        if added:
            self._logger.debug('Adding participants: %r' % added)
        if removed:
            self._logger.debug('Removing participants: %r' % removed)
        for handle, bus_name in added:
            buddy = self._get_buddy(handle)
            if buddy is not None:
                self._logger.debug('Buddy %s was added' % buddy.props.nick)
        for handle in removed:
            buddy = self._get_buddy(handle)
            if buddy is not None:
                self._logger.debug('Buddy %s was removed' % buddy.props.nick)
                # Set buddy's polls to not active so I can't vote on them
                for poll in self.activity._polls:
                    if poll.author == buddy.props.nick:
                        poll.active = False
                        self._logger.debug(
                            'Closing poll %s of %s who just left.' %
                            (poll.title, poll.author))

        if not self.entered:
            if self.is_initiator:
                self._logger.debug("I'm initiating the tube")
            else:
                self._logger.debug('Joining, sending Hello')
                self.Hello()
            self.tube.add_signal_receiver(self.hello_cb, 'Hello', IFACE,
                path=PATH, sender_keyword='sender')
            self.tube.add_signal_receiver(self.vote_cb, 'Vote', IFACE,
                path=PATH, sender_keyword='sender')
            self.tube.add_signal_receiver(self.helloback_cb, 'HelloBack',
                IFACE, path=PATH, sender_keyword='sender')
            self.tube.add_signal_receiver(self.updatedpoll_cb, 
                'UpdatedPoll', IFACE, path=PATH, sender_keyword='sender')
            self.my_bus_name = self.tube.get_unique_name()
            self.entered = True

    @signal(dbus_interface=IFACE, signature='')
    def Hello(self):
        """Request that my UpdatePoll method is called to let me know about
        other known polls.
        """

    @signal(dbus_interface=IFACE, signature='ssus')
    def Vote(self, author, title, choice, votersha):
        """Send my vote on author's poll.

        author -- string, buddy name
        title -- string, poll title
        choice -- integer 0-4, selected vote
        votersha -- string, sha1 of voter's nick
        """

    @signal(dbus_interface=IFACE, signature='s')
    def HelloBack(self, recipient):
        """Respond to Hello.

        recipient -- string, sender of Hello.
        """

    @signal(dbus_interface=IFACE, signature='ssuuusua{us}a{uu}a{su}')
    def UpdatedPoll(self, title, author, active, createdate, maxvoters,
                   question, number_of_options, options, data, votes):
        """Broadcast a new poll to the mesh."""

    def hello_cb(self, sender=None):
        """Tell the newcomer what's going on."""
        assert sender is not None
        self._logger.debug('Newcomer %s has joined and sent Hello', sender)
        # sender is a bus name - check if it's me:
        if sender == self.my_bus_name:
            # then I don't want to respond to my own Hello
            return
        # Send my polls
        for poll in self.activity.get_my_polls():
            self._logger.debug('Telling %s about my %s' % 
                               (sender, poll.title))
            self.tube.get_object(sender, PATH).UpdatePoll(
                poll.title, poll.author, int(poll.active),
                poll.createdate.toordinal(),
                poll.maxvoters, poll.question, poll.number_of_options,
                poll.options, poll.data, poll.votes, dbus_interface=IFACE)
        # Ask for other's polls back
        self.HelloBack(sender)

    def helloback_cb(self, recipient, sender):
        """Reply to Hello.
        
        recipient -- string, the XO who send the original Hello.
        
        Other XOs should ignore this signal.
        """
        self._logger.debug('*** In helloback_cb: recipient: %s, sender: %s' %
                           (recipient, sender))
        if sender == self.my_bus_name:
            # Ignore my own signal
            return
        if recipient != self.my_bus_name:
            # This is not for me
            return
        self._logger.debug('*** It was for me, so sending my polls back.')
        for poll in self.activity.get_my_polls():
            self._logger.debug('Telling %s about my %s' % 
                               (sender, poll.title))
            self.tube.get_object(sender, PATH).UpdatePoll(
                poll.title, poll.author, int(poll.active),
                poll.createdate.toordinal(),
                poll.maxvoters, poll.question, poll.number_of_options,
                poll.options, poll.data, poll.votes, dbus_interface=IFACE)

    def updatedpoll_cb(self, title, author, active, createdate, maxvoters,
                       question, number_of_options, options_d, data_d,
                       votes_d, sender):
        """Handle an UpdatedPoll signal by creating a new Poll."""
        self._logger.debug('Received UpdatedPoll from %s' % sender)
        if sender == self.my_bus_name:
            # Ignore my own signal
            return
        # We get the parameters as dbus types. These are not serialisable
        # with pickle at the moment, so convert them to builtin types.
        # Pay special attention to dicts - we need to convert the keys
        # and values too.
        title = str(title)
        author = str(author)
        active = bool(active)
        createdate = date.fromordinal(int(createdate))
        maxvoters = int(maxvoters)
        question = str(question)
        number_of_options = int(number_of_options)
        options = {}
        for key in options_d:
            value = options_d[key]
            options[int(key)] = str(value)
        data = {}
        for key in data_d:
            value = data_d[key]
            data[int(key)] = int(value)
        votes = {}
        for key in votes_d:
            value = votes_d[key]
            votes[str(key)] = int(value)
        poll = Poll(self.activity, title, author, active, 
                    createdate, maxvoters, question, number_of_options,
                    options, data, votes)
        self.activity._polls.add(poll)
        self.activity.alert(_('New Poll'),
                            _("%(author)s shared a poll "
                              "'%(title)s' with you.") % {'author': author,
                                                          'title': title})

    def vote_cb(self, author, title, choice, votersha, sender=None):
        """Receive somebody's vote signal.

        author -- string, buddy name
        title -- string, poll title
        choice -- integer 0-4, selected vote
        votersha -- string, sha1 hash of voter nick
        """
        # FIXME: validate the choices, set the vote.
        # XXX We could possibly get the nick of sender and sha1 it
        #     to verify the vote is coming from the voter.
        if sender == self.my_bus_name:
            # Don't respond to my own Vote signal
            return
        self._logger.debug('In vote_cb. sender: %r' % sender)
        self._logger.debug('%s voted %d on %s by %s' % (votersha, choice,
                                                        title, author))
        self.activity.vote_on_poll(author, title, choice, votersha)

    @method(dbus_interface=IFACE, in_signature='ssuuusua{us}a{uu}a{su}',
            out_signature='')
    def UpdatePoll(self, title, author, active, createdate, maxvoters,
                   question, number_of_options, options_d, data_d, votes_d):
        """To be called on the incoming buddy by the other participants
        to inform you of their polls and state."""
        # We get the parameters as dbus types. These are not serialisable
        # with pickle at the moment, so convert them to builtin types.
        # Pay special attention to dicts - we need to convert the keys
        # and values too.
        title = str(title)
        author = str(author)
        active = bool(active)
        createdate = date.fromordinal(int(createdate))
        maxvoters = int(maxvoters)
        question = str(question)
        number_of_options = int(number_of_options)
        options = {}
        for key in options_d:
            value = options_d[key]
            options[int(key)] = str(value)
        data = {}
        for key in data_d:
            value = data_d[key]
            data[int(key)] = int(value)
        votes = {}
        for key in votes_d:
            value = votes_d[key]
            votes[str(key)] = int(value)
        poll = Poll(self.activity, title, author, active, 
                    createdate, maxvoters, question, number_of_options,
                    options, data, votes)
        self.activity._polls.add(poll)
        self.activity.alert(_('New Poll'),
                            _("%(author)s shared a poll "
                              "'%(title)s' with you.") % {'author': author,
                                                          'title': title})

    @method(dbus_interface=IFACE, in_signature='s', out_signature='')
    def PollsWanted(self, sender):
        """Notification to send my polls to sender."""
        for poll in self.activity.get_my_polls():
            self.tube.get_object(sender, PATH).UpdatePoll(
                poll.title, poll.author, int(poll.active),
                poll.createdate.toordinal(),
                poll.maxvoters, poll.question, poll.number_of_options,
                poll.options, poll.data, poll.votes, dbus_interface=IFACE)


def justify(textdict, choice):
    """Take a {} of numbers, and right justify the chosen item.

    textdict is a dict of {n: m} where n and m are integers.
    choice is one of textdict.keys()

    Returns a string of '   m' with m right-justified
    so that the longest value in the dict can fit.
    """
    max_len = 0
    for num in textdict.values():
        if len(str(num)) > max_len:
            max_len = len(str(num))
    value = str(textdict[choice])
    return value.rjust(max_len)


class LessonPlanWidget (gtk.Notebook):
    def __init__ (self, basepath):
        """Create a Notebook widget for displaying lesson plans in tabs.

        basepath -- string, path of directory containing lesson plans.
        """
        super(LessonPlanWidget, self).__init__()
        lessons = filter(lambda x: os.path.isdir(os.path.join(basepath,
                                                              'lessons', x)),
                         os.listdir(os.path.join(basepath, 'lessons')))
        lessons.sort()
        for lesson in lessons:
            self._load_lesson(os.path.join(basepath, 'lessons', lesson),
                              _(lesson))

    def _load_lesson (self, path, name):
        """Load the lesson content from a .abw, taking l10n into account.

        path -- string, path of lesson plan file, e.g. lessons/Introduction
        lesson -- string, name of lesson
        """
        code, encoding = locale.getdefaultlocale()
        canvas = AbiCanvas()
        canvas.show()
        files = map(lambda x: os.path.join(path, '%s.abw' % x),
                    ('_'+code.lower(), '_'+code.split('_')[0].lower(), 
                     'default'))
        files = filter(lambda x: os.path.exists(x), files)
        canvas.load_file('file://%s' % files[0], '')
        canvas.view_online_layout()
        canvas.zoom_width()
        canvas.set_show_margin(False)
        self.append_page(canvas, gtk.Label(name))
