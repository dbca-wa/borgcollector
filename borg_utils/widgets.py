import copy

from django.forms.widgets import Widget, Media
from django.utils.safestring import mark_safe


class MultiWidgetLayout(Widget):
    """
    Django's built-in MultiWidget is a widget that is composed of multiple widgets.
    MutliWidtetLayout implements the same concept but the rendering of the composed 
    output can be controlled using a layout.
    When subclassing it, you need to call parent constructor passing:
    * layout: A list that contains the layout you want to be rendered. i.e:
        layout = [ 
            "<label for='%(id)s'>Street:</label>", TextInput(),
            "<label for='%(id)s'>Number:</label>", TextInput(),
            "<label for='%(id)s'>Zip Code:</label>", TextInput()
        ]
    The constructor builds a list of widgets named self.widgets iterating over
    the layout.
    Its render() method is different than other widgets', because it has to
    figure out how to split a single value for display in multiple widgets.
    The ``value`` argument can be one of two things:
        * A list.
        * A normal value (e.g., a string) that has been "compressed" from
          a list of values.
    The render() method calls:
    * render_setup(): This marks self.widgets as localized if necessary,
    if the value is NOT a list it calls decompress to turn it into a list.
    MultiWidgetLayout subclasses must implement decompress(), which takes a 
    single "compressed" value and returns a list. 
    render_setup() returns a tuple used for rendering the layout in the next step.
    * render_layout(): It iterates over self.layout. If the field is a widget,
    it renders the widget with its corresponding value. Otherwise, it adds the 
    string formatted using final_attrs as its context.
    You'll probably want to use this class with MultiValueField.
    """
    def __init__(self, layout, attrs=None):
        self.layout = layout
        self.widgets = []

        for field in self.layout:
            if not isinstance(field, basestring):
                self.widgets.append(field)
 
        super(MultiWidgetLayout, self).__init__(attrs)

    def render_setup(self, name, value, attrs=None):
        if self.is_localized:
            for widget in self.widgets:
                widget.is_localized = self.is_localized
       
        # value should be a list of values mapping to self.widgets
        if not isinstance(value, list):
            value = self.decompress(value)

        final_attrs = self.build_attrs(attrs)
        id_ = final_attrs.get('id', None)

        return (value, final_attrs, id_)

    def render_layout(self, name, value, final_attrs=None, id_=None):
        html = ""
        i = 0
        for field in self.layout:
            if id_ and final_attrs.get('id', '') != "%s_%s" % (id_, i):
                final_attrs = dict(final_attrs, id='%s_%s' % (id_, i))

            if not isinstance(field, basestring):
                try:
                    widget_value = value[i]
                except IndexError:
                    widget_value = None

                html += self.widgets[i].render(name + '_%s' % i, widget_value, final_attrs)
                i += 1
            else:
                html += field % final_attrs

        return html

    def render(self, name, value, attrs=None):
        value, final_attrs, id_ = self.render_setup(name, value, attrs)
        return mark_safe(self.render_layout(name, value, final_attrs, id_))

    def id_for_label(self, id_):
        # See the comment for RadioSelect.id_for_label()
        if id_:
            id_ += '_0'
        return id_
    id_for_label = classmethod(id_for_label)

    def value_from_datadict(self, data, files, name):
        return [widget.value_from_datadict(data, files, name + '_%s' % i) for i, widget in enumerate(self.widgets)]

    def decompress(self, value):
        """
        Returns a list of decompressed values for the given compressed value.
        The given value can be assumed to be valid, but not necessarily
        non-empty.
        """
        raise NotImplementedError('Subclasses must implement this method.')

    def _get_media(self):
        "Media for a multiwidget is the combination of all media of the subwidgets"
        media = Media()
        for w in self.widgets:
            media = media + w.media
        return media
    media = property(_get_media)

    def __deepcopy__(self, memo):
        obj = super(MultiWidgetLayout, self).__deepcopy__(memo)
        obj.widgets = copy.deepcopy(self.widgets)
        obj.layout = copy.deepcopy(self.layout)
        return obj
