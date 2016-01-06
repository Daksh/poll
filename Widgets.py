#!/usr/bin/env python
# -*- coding: utf-8 -*-

#   Widgets.py por:
#   Flavio Danesse <fdanesse@gmail.com>
#   CeibalJAM! - Uruguay

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

import os
import locale

from gettext import gettext as _

from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GdkPixbuf

from sugar3 import mime
from sugar3 import profile
from sugar3.graphics.objectchooser import ObjectChooser

from sugar3.graphics.toolbarbox import ToolbarBox
from sugar3.graphics.toolbutton import ToolButton
from sugar3.activity.widgets import StopButton
from sugar3.activity.widgets import ActivityToolbarButton
from sugar3.graphics.style import Color

basepath = os.path.dirname(__file__)


class Toolbar(ToolbarBox):

    def __init__(self, activity):

        ToolbarBox.__init__(self)

        activity_button = ActivityToolbarButton(activity)
        self.toolbar.insert(activity_button, 0)
        activity_button.show()

        separator = Gtk.SeparatorToolItem()
        self.toolbar.insert(separator, -1)

        self.choose_button = ToolButton('view-list')
        self.choose_button.set_tooltip(_('Choose a Poll'))
        self.toolbar.insert(self.choose_button, -1)

        self.create_button = ToolButton('view-source')
        self.create_button.set_tooltip(_('Build a Poll'))
        self.toolbar.insert(self.create_button, -1)

        self.settings_button = ToolButton('preferences-system')
        self.settings_button.set_tooltip(_('Settings'))
        self.toolbar.insert(self.settings_button, -1)

        self.help_button = ToolButton('toolbar-help')
        self.help_button.set_tooltip(_('Lesson Plans'))
        self.toolbar.insert(self.help_button, -1)

        separator = Gtk.SeparatorToolItem()
        separator.props.draw = False
        separator.set_expand(True)
        self.toolbar.insert(separator, -1)
        separator.show()

        self.toolbar.insert(StopButton(activity), -1)

        self.show_all()


class NewPollCanvas(Gtk.Box):
    """
    widgets to set up a new poll or editing existing poll.
        editing is False to start a new poll.
        editing is True to edit the current poll.

    highlight is a list of strings denoting items failing validation.
    """

    def __init__(self, poll, editing=False, highlight=[]):

        # FIXME: El parámetro highlight nunca se utilizó, la idea era
        # resaltar el texto en las etiquetas para aquellas opciones no
        # validadas en la encuesta.
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL)

        self._poll = poll

        self._poll.activity._current_view = 'build'

        label = Gtk.Label()
        label.set_markup('<big><b>%s</b></big>' % _('Build a poll'))
        self.pack_start(label, False, False, 10)

        item_poll = ItemNewPoll(_('Poll Title:'), self._poll.title)
        item_poll.entry.connect('changed', self.__entry_activate_cb, 'title')
        self.pack_start(item_poll, False, False, 10)

        item_poll = ItemNewPoll(_('Question:'), self._poll.question)
        item_poll.entry.connect('changed', self.__entry_activate_cb,
                                'question')
        self.pack_start(item_poll, False, False, 10)

        item_poll = ItemNewPoll(_('Number of votes to collect:'),
                                str(self._poll.maxvoters))
        item_poll.entry.connect('changed', self.__entry_activate_cb,
                                'maxvoters')
        self.pack_start(item_poll, False, False, 10)

        for choice in self._poll.options.keys():
            hbox = Gtk.HBox()
            item_poll = ItemNewPoll(_('Answer %s:') % choice,
                                    self._poll.options[choice])
            item_poll.entry.connect('changed', self.__entry_activate_cb,
                                    str(choice))
            self.pack_start(item_poll, False, False, 10)

            if self._poll.activity._use_image:
                if self.__already_loaded_image_in_answer(choice):
                    button = Gtk.Button(_("Change Image"))
                    hbox.pack_start(button, True, False, 10)
                    self.__show_image_thumbnail(hbox, choice)

                else:
                    button = Gtk.Button(_("Add Image"))
                    hbox.pack_start(button, True, False, 10)

                button.connect('clicked', self.__button_choose_image_cb,
                               str(choice), hbox)

            item_poll.pack_end(hbox, False, False, 0)

        # PREVIEW & SAVE buttons
        hbox = Gtk.HBox()

        button = Gtk.Button(_("Step 1: Preview"))
        button.connect('clicked', self.__button_preview_cb)
        hbox.pack_start(button, True, True, 10)

        button = Gtk.Button(_("Step 2: Save"))
        button.connect('clicked', self._button_save_cb)
        hbox.pack_start(button, True, True, 10)

        self.pack_start(hbox, False, False, 10)

        self.show_all()

    def __already_loaded_image_in_answer(self, answer_number):

        if not self._poll.images_ds_objects[int(answer_number)] == {}:
            return True

        else:
            return False

    def __button_choose_image_cb(self, button, data=None, data2=None):

        if hasattr(mime, 'GENERIC_TYPE_IMAGE'):
            chooser = ObjectChooser(parent=self,
                                    what_filter=mime.GENERIC_TYPE_IMAGE)
        else:
            chooser = ObjectChooser(parent=self)

        try:
            result = chooser.run()

            if result == Gtk.ResponseType.ACCEPT:

                jobject = chooser.get_selected_object()

                images_mime_types = mime.get_generic_type(
                    mime.GENERIC_TYPE_IMAGE).mime_types

                if jobject and jobject.file_path and \
                   jobject.metadata.get('mime_type') in images_mime_types:

                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                        jobject.file_path,
                        self._poll.activity._image_size['height'],
                        self._poll.activity._image_size['width'])

                    self._poll.images[int(data)] = pixbuf

                    self._poll.images_ds_objects[int(data)]['id'] = \
                        jobject.object_id

                    self._poll.images_ds_objects[int(data)]['file_path'] = \
                        jobject.file_path

                    self.__show_image_thumbnail(data2, data)
                    button.set_label(_('Change Image'))

                else:
                    self._poll.activity.get_alert(
                        _('Poll Activity'),
                        _('Your selection is not an image'))

        finally:
            chooser.destroy()
            del chooser

    def __show_image_thumbnail(self, parent_box, answer_number):

        hbox = Gtk.HBox()

        image_file_path = self._poll.images_ds_objects[int(answer_number)][
            'file_path']

        pixbuf_thumbnail = GdkPixbuf.Pixbuf.new_from_file_at_size(
            image_file_path, 80, 80)

        image = Gtk.Image()
        image.set_from_pixbuf(pixbuf_thumbnail)
        image.show()
        hbox.add(image)
        hbox.show()

        chl = parent_box.get_children()

        if len(chl) == 4:
            parent_box.remove(chl[len(chl) - 1])

        parent_box.pack_start(hbox, True, True, 0)

    def _button_save_cb(self, button):
        """
        Save button clicked.
        """

        ### Validate data
        failed_items = self.__validate()

        if failed_items:
            print "*** failed_items:", failed_items
            # FIXME: El parámetro highlight nunca se utilizó, la idea era
            # resaltar el texto en las etiquetas para aquellas opciones no
            # validadas en la encuesta.
            # (Modificar para que suceda al perder el foco el entry)
            #self.set_root(self._build_canvas(highlight=failed_items))
            #self.show_all()
            return

        # Data OK
        self._poll.activity._previewing = False
        self._poll.active = True
        self._poll.activity._polls.add(self._poll)
        self._poll.broadcast_on_mesh()
        self._poll.activity.set_canvas(self._poll.activity._poll_canvas())
        self._poll.activity.show_all()

    def __button_preview_cb(self, button):
        """
        Preview button clicked.
        """

        # Validate data
        failed_items = self.__validate()

        if failed_items:
            print "*** failed_items:", failed_items
            # FIXME: El parámetro highlight nunca se utilizó, la idea era
            # resaltar el texto en las etiquetas para aquellas opciones no
            # validadas en la encuesta.
            # (Modificar para que suceda al perder el foco el entry)
            #self.set_root(self._build_canvas(highlight=failed_items))
            #self.show_all()
            return

        # Data OK
        self._poll.active = True  # Show radio buttons
        self._poll.activity._previewing = True
        self._poll.activity.set_canvas(self._poll.activity._poll_canvas())
        self._poll.activity.show_all()

    def __validate(self):

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

    def __entry_activate_cb(self, entry, data):

        text = entry.get_text()

        if text:
            if data == 'title':
                self._poll.title = text

            elif data == 'question':
                self._poll.question = text

            elif data == 'maxvoters':
                try:
                    self._poll.maxvoters = int(text)

                except ValueError:
                    self._poll.maxvoters = 0  # invalid, will be trapped

            else:
                self._poll.options[int(data)] = text


class ItemNewPoll(Gtk.Box):

    def __init__(self, label_text, entry_text):

        Gtk.Box.__init__(self, orientation=Gtk.Orientation.HORIZONTAL)

        self.entry = Gtk.Entry()
        self.entry.set_text(entry_text)

        self.pack_start(Gtk.Label(label_text), False, False, 10)
        self.pack_start(self.entry, True, True, 10)

        self.show_all()


class OptionsCanvas(Gtk.Box):
    """
    Show the options canvas.
    """

    def __init__(self, poll_activity):

        Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL)

        self.poll_activity = poll_activity
        self.poll_activity._current_view = 'options'

        alignment = Gtk.Alignment.new(0.5, 0, 0, 0)
        optionsbox = Gtk.VBox()

        alignment.add(optionsbox)
        self.pack_start(alignment, True, True, 0)

        mainbox = Gtk.VBox()

        optionsbox.pack_start(mainbox, True, False, 0)

        label = Gtk.Label()
        label.set_markup('<big><b>%s</b></big>' % _('Settings'))
        mainbox.pack_start(label, False, False, 10)

        options_details_box = Gtk.VBox()
        mainbox.pack_start(options_details_box, True, False, 10)

        viewResultCB = Gtk.CheckButton(label=_('Show answers while voting'))
        viewResultCB.set_active(self.poll_activity._view_answer)
        viewResultCB.connect('toggled', self.__view_result_checkbox_cb)
        options_details_box.pack_start(viewResultCB, True, True, 10)

        rememberVoteCB = Gtk.CheckButton(label=_('Remember last vote'))
        rememberVoteCB.set_active(self.poll_activity._remember_last_vote)
        rememberVoteCB.connect('toggled',
                               self.__remember_last_vote_checkbox_cb)
        options_details_box.pack_start(rememberVoteCB, True, True, 10)

        playVoteSoundCB = Gtk.CheckButton(
            label=_('Play a sound when make a vote'))
        playVoteSoundCB.set_active(self.poll_activity._play_vote_sound)
        playVoteSoundCB.connect('toggled', self.__play_vote_sound_checkbox_cb)
        options_details_box.pack_start(playVoteSoundCB, True, True, 10)

        vbox = Gtk.VBox()
        useImageCB = Gtk.CheckButton(label=_('Use image in answer'))
        useImageCB.set_active(self.poll_activity._use_image)
        options_details_box.pack_start(useImageCB, True, True, 10)

        hbox2 = Gtk.HBox()
        hbox2.pack_start(Gtk.Label(_('Image Size: ')), True, True, 10)
        entrybox = Gtk.Entry(max_length=3)

        #entrybox.modify_bg(Gtk.StateType.INSENSITIVE,
        #    style.COLOR_WHITE.get_gdk_color())

        entrybox.set_text(str(self.poll_activity._image_size['height']))
        entrybox.connect('changed', self.__entry_image_size_cb, 'height')
        hbox2.pack_start(entrybox, True, True, 10)
        hbox2.pack_start(Gtk.Label('x'), True, True, 10)
        entrybox = Gtk.Entry(max_length=3)

        #entrybox.modify_bg(Gtk.StateType.INSENSITIVE,
        #    style.COLOR_WHITE.get_gdk_color())

        entrybox.set_text(str(self.poll_activity._image_size['width']))
        entrybox.connect('changed', self.__entry_image_size_cb, 'width')
        hbox2.pack_start(entrybox, True, True, 10)
        useImageCB.connect('toggled', self.__use_image_checkbox_cb, vbox,
                           hbox2)

        if self.poll_activity._use_image:
            vbox.pack_start(hbox2, True, True, 10)

        options_details_box.pack_start(vbox, True, True, 0)

        hbox = Gtk.HBox()
        # SAVE button
        button = Gtk.Button(_("Save"))
        button.connect('clicked', self.__button_save_options_cb)
        hbox.pack_start(button, True, True, 10)

        options_details_box.pack_end(hbox, True, True, 10)

        self.show_all()

    def __view_result_checkbox_cb(self, checkbox):
        self.poll_activity._view_answer = checkbox.get_active()

    def __remember_last_vote_checkbox_cb(self, checkbox):
        self.poll_activity._remember_last_vote = checkbox.get_active()

    def __play_vote_sound_checkbox_cb(self, checkbox, data=None):
        self.poll_activity._play_vote_sound = checkbox.get_active()

    def __entry_image_size_cb(self, entrycontrol, data):

        text = entrycontrol.get_text()

        if text:
            self.poll_activity._image_size[data] = int(text)

    def __use_image_checkbox_cb(self, checkbox, parent, child):

        self.poll_activity._use_image = checkbox.get_active()

        if checkbox.get_active():
            parent.pack_start(child, True, True, 0)

        else:
            parent.remove(child)

        self.show_all()

    def __button_save_options_cb(self, button):

        self.poll_activity.get_alert(
            _('Poll Activity'),
            _('The settings have been saved'))


class SelectCanvas(Gtk.Box):

    def __init__(self, poll_activity):

        Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL)

        poll_activity._current_view = 'select'

        label = Gtk.Label()
        label.set_markup('<big><b>%s</b></big>' % _('Choose a Poll'))
        self.pack_start(label, False, False, 0)

        poll_selector_box = Gtk.VBox()

        scroll = Gtk.ScrolledWindow()

        scroll.set_policy(
            Gtk.PolicyType.AUTOMATIC,
            Gtk.PolicyType.NEVER)

        scroll.add_with_viewport(poll_selector_box)

        self.pack_start(scroll, True, True, 10)

        row_number = 0

        for poll in poll_activity._polls:
            sha = poll.sha

            """
            if row_number % 2:
                row_bgcolor = style.COLOR_WHITE.get_int()

            else:
                row_bgcolor = style.COLOR_SELECTION_GREY.get_int()
            """

            row_number += 1

            poll_row = Gtk.HBox()
            poll_selector_box.pack_start(poll_row, False, False, 10)

            title = Gtk.Label(label=poll.title + ' (' + poll.author + ')')
            align = Gtk.Alignment.new(0, 0.5, 0, 0)
            align.add(title)
            poll_row.pack_start(align, True, True, 10)

            if poll.active:
                button = Gtk.Button(_('VOTE'))

            else:
                button = Gtk.Button(_('SEE RESULTS'))

            button.connect('clicked', poll_activity._select_poll_button_cb,
                           sha)
            poll_row.pack_start(button, False, False, 10)

            if poll.author == profile.get_nick_name():
                button = Gtk.Button(_('DELETE'))
                button.connect('clicked',
                               poll_activity._delete_poll_button_cb, sha)
                poll_row.pack_start(button, False, False, 10)

            poll_row.pack_start(Gtk.Label(
                poll.createdate.strftime('%d/%m/%y')), False, False, 10)

        self.show_all()


class LessonPlanCanvas(Gtk.Box):

    # This strings are needed to l10n of the tabs
    tabs_labels = [_("Introduction"), _("Lesson 1"), _("Lesson 2"),
                   _("Lesson 3"), _("Lesson 4")]

    def __init__(self, poll_activity):

        Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL)

        poll_activity._current_view = 'lessonplan'

        label = Gtk.Label()
        label.set_markup('<big><b>%s</b></big>' % _('Lesson Plans'))
        self.pack_start(label, False, False, 10)
        self.pack_start(LessonPlanWidget(), True, True, 0)

        self.show_all()


class LessonPlanWidget(Gtk.Notebook):
    """
    Create a Notebook widget for displaying lesson plans in tabs.

    basepath -- string, path of directory containing lesson plans.
    """

    def __init__(self):

        Gtk.Notebook.__init__(self)

        lessons = filter(
            lambda x: os.path.isdir(os.path.join(basepath,
                                                 'lessons', x)),
            os.listdir(os.path.join(basepath, 'lessons')))

        lessons.sort()

        for lesson in lessons:
            self.__load_lesson(
                os.path.join(basepath, 'lessons', lesson),
                _(lesson))

        self.show_all()

    def __load_lesson(self, path, name):
        """
        Load the lesson content from a .txt, taking l10n into account.

        path -- string, path of lesson plan file, e.g. lessons/Introduction
        lesson -- string, name of lesson
        """
        code, encoding = locale.getdefaultlocale()
        if code is None:
            code = 'en'
        files = map(
            lambda x: os.path.join(path, '%s.txt' % x),
            ('_' + code.lower(), '_' + code.split('_')[0].lower(),
             'default'))

        files = filter(lambda x: os.path.exists(x), files)

        canvas = Gtk.TextView();
        canvas.set_wrap_mode(Gtk.WrapMode.WORD)
        with open(files[0],'r') as f:
            text = f.read()
            canvas.get_buffer().set_text(text)
        
        self.append_page(canvas, Gtk.Label(label=name))


class PollCanvas(Gtk.Box):

    def __init__(self, cabecera, poll, current_vote, view_answer, previewing):

        Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL)

        self._poll = poll

        self.cabecera = Gtk.Label()
        self.cabecera.set_markup('<big><b>%s</b></big>' % _(cabecera))
        self.pack_start(self.cabecera, False, False, 10)

        self.title = Gtk.Label(poll.title)
        self.title.set_alignment(0.01, 0.5)
        self.pack_start(self.title, False, False, 10)

        self.question = Gtk.Label(poll.question)
        self.question.set_alignment(0.01, 0.5)
        self.pack_start(self.question, False, False, 10)

        frame = Gtk.AspectFrame()
        tabla = Gtk.Table(rows=6, columns=6)
        tabla.set_border_width(20)

        frame.add(tabla)

        eventbox = Gtk.EventBox()
        eventbox.set_border_width(20)
        eventbox.modify_bg(0, Gdk.Color(65000, 65000, 65000))
        eventbox.add(frame)

        scroll = Gtk.ScrolledWindow()

        scroll.set_policy(
            Gtk.PolicyType.AUTOMATIC,
            Gtk.PolicyType.AUTOMATIC)

        scroll.add_with_viewport(eventbox)

        self.pack_start(scroll, True, True, 10)

        group = Gtk.RadioButton()

        xo_color = profile.get_color()

        row = 0
        for choice in range(poll.number_of_options):

            button = Gtk.RadioButton.new_with_label_from_widget(
                group, poll.options[choice])

            button.connect('toggled', poll.activity.vote_choice_radio_button,
                           choice)

            if poll.active:
                button.set_sensitive(True)
            else:
                button.set_sensitive(False)

            tabla.attach(button, 0, 1, row, row+1)

            if choice == current_vote:
                button.set_active(True)

            if not poll.images[int(choice)] == '':
                image = Gtk.Image()
                image.set_from_pixbuf(poll.images[choice])
                tabla.attach(image, 1, 2, row, row + 1)

            if view_answer or not poll.active:
                if poll.vote_count > 0:

                    ### Total de votos
                    label = Gtk.Label(poll.data[choice])
                    label.set_size_request(100, -1)
                    tabla.attach(label, 3, 4, row, row + 1)

                    eventbox = Gtk.EventBox()
                    eventbox.set_size_request(300, -1)
                    tabla.attach(eventbox, 4, 5, row, row + 1)

                    eventbox.connect("draw",
                                     self.__draw_bar, poll.data[choice],
                                     poll.vote_count, xo_color)

            row += 1

        if view_answer or not poll.active:
            if poll.vote_count > 0:
                ### Barra para total
                separator = Gtk.HSeparator()
                tabla.attach(separator, 3, 5, row, row + 1)

        row += 1

        if view_answer or not poll.active:
            if poll.vote_count > 0:
                label = Gtk.Label("%s %s %s %s" % (str(poll.vote_count),
                                  _('votes'), _('(votes left to collect)'),
                                  poll.maxvoters - poll.vote_count))
                tabla.attach(label, 3, 5, row, row + 1)

        row += 1

        # Button area
        if poll.active and not previewing:
            button = Gtk.Button(_("Vote"))
            button.connect('clicked', poll.activity.button_vote_cb)
            button.props.margin = 10
            tabla.attach(button, 0, 1, row, row + 1)

        elif previewing:
            button = Gtk.Button(_("Edit Poll"))
            button.connect('clicked', poll.activity.button_edit_clicked)
            button.props.margin = 10
            tabla.attach(button, 0, 1, row, row + 1)

            button = Gtk.Button(_("Save Poll"))
            button.connect('clicked', self._button_save_cb)
            button.props.margin = 10
            tabla.attach(button, 1, 2, row, row + 1)

        self.show_all()

    def _button_save_cb(self, button):
        """
        Save button clicked.
        """

        ### Validate data
        failed_items = self.__validate()

        if failed_items:
            print "*** failed_items:", failed_items
            # FIXME: El parámetro highlight nunca se utilizó, la idea era
            # resaltar el texto en las etiquetas para aquellas opciones no
            # validadas en la encuesta.
            # (Modificar para que suceda al perder el foco el entry)
            #self.set_root(self._build_canvas(highlight=failed_items))
            #self.show_all()
            return

        # Data OK
        self._poll.activity._previewing = False
        self._poll.active = True
        self._poll.activity._polls.add(self._poll)
        self._poll.broadcast_on_mesh()
        self._poll.activity.set_canvas(self._poll.activity._poll_canvas())
        self._poll.activity.show_all()

    def __validate(self):

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

    def __draw_bar(self, widget, context, votos, total, xo_color):
        """
        Graphic the percent of votes from one option.
        """
        stroke_color = Color(xo_color.get_stroke_color())
        fill_color = Color(xo_color.get_fill_color())

        rect = widget.get_allocation()
        w, h = (rect.width, rect.height)
        percent = votos * 100 / total
        width = w * percent / 100

        context.rectangle(0, h / 2 - 10, width, 20)
        context.set_source_rgba(*fill_color.get_rgba())
        context.fill_preserve()
        context.set_source_rgba(*stroke_color.get_rgba())
        context.set_line_width(3)
        context.stroke()

        return True
