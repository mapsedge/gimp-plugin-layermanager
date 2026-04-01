#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import gi
gi.require_version('Gimp', '3.0')
gi.require_version('GimpUi', '3.0')
gi.require_version('Gtk', '3.0')
from gi.repository import Gimp, GimpUi, GLib, Gtk
import sys

#------------------------------------------------------------------------------
# Layer helpers
#------------------------------------------------------------------------------
def get_all_layers(image):
    result = []
    def _walk(layers):
        for layer in layers:
            result.append(layer)
            children = layer.get_children() if hasattr(layer, 'get_children') else []
            if children:
                _walk(children)
    _walk(image.get_layers())
    return result

def get_active_layer(image, drawables=None):
    if drawables:
        for d in drawables:
            if isinstance(d, Gimp.Layer):
                return d
    selected = image.get_selected_drawables()
    for d in selected:
        if isinstance(d, Gimp.Layer):
            return d
    layers = image.get_layers()
    return layers[0] if layers else None

def get_active_index(image, drawables=None):
    active = get_active_layer(image, drawables)
    if not active:
        return -1
    active_id = active.get_id()
    for i, layer in enumerate(get_all_layers(image)):
        if layer.get_id() == active_id:
            return i
    return -1

def get_all_children(layer):
    result = []
    children = layer.get_children() if hasattr(layer, 'get_children') else []
    for child in children:
        result.append(child)
        result.extend(get_all_children(child))
    return result

def get_ignored(image):
    """Return set of layer IDs marked as ignored via parasite.
    If a group is ignored, all its descendants are also ignored."""
    ignored = set()
    for layer in get_all_layers(image):
        try:
            if layer.get_parasite('lm-ignore'):
                ignored.add(layer.get_id())
                for child in get_all_children(layer):
                    ignored.add(child.get_id())
        except Exception:
            pass
    return ignored

def is_group(layer):
    return isinstance(layer, Gimp.GroupLayer)

def active_is_group(drawables):
    if drawables:
        for d in drawables:
            if isinstance(d, Gimp.Layer):
                return is_group(d)
    return False

def type_filter(layers, drawables):
    """Keep only layers matching the type (group vs non-group) of the active layer."""
    if active_is_group(drawables):
        return [l for l in layers if is_group(l)]
    else:
        return [l for l in layers if not is_group(l)]

def layers_selected(image, drawables=None):
    ignored = get_ignored(image)
    selected = image.get_selected_drawables()
    return [d for d in selected if isinstance(d, Gimp.Layer) and d.get_id() not in ignored]

def layers_above(image, drawables=None):
    idx = get_active_index(image, drawables)
    if idx < 0: return []
    ignored = get_ignored(image)
    candidates = [l for l in get_all_layers(image)[:idx] if l.get_id() not in ignored]
    return type_filter(candidates, drawables)

def layers_below(image, drawables=None):
    idx = get_active_index(image, drawables)
    if idx < 0: return []
    ignored = get_ignored(image)
    candidates = [l for l in get_all_layers(image)[idx + 1:] if l.get_id() not in ignored]
    return type_filter(candidates, drawables)

def layers_other(image, drawables=None):
    idx = get_active_index(image, drawables)
    if idx < 0: return []
    all_layers = get_all_layers(image)
    ignored = get_ignored(image)
    candidates = [l for l in (all_layers[:idx] + all_layers[idx + 1:]) if l.get_id() not in ignored]
    return type_filter(candidates, drawables)

def layers_all(image, drawables=None):
    ignored = get_ignored(image)
    candidates = [l for l in get_all_layers(image) if l.get_id() not in ignored]
    return type_filter(candidates, drawables)

def apply_op(image, layers, op):
    image.undo_group_start()
    for layer in layers:
        op(layer)
    image.undo_group_end()
    Gimp.displays_flush()

def match_filter(name, pattern):
    if not pattern or pattern == '*':
        return True
    name = name.lower()
    pattern = pattern.lower()
    if pattern.endswith('*') and not pattern.startswith('*'):
        return name.startswith(pattern[:-1])
    if pattern.startswith('*') and not pattern.endswith('*'):
        return name.endswith(pattern[1:])
    return pattern.strip('*') in name

def filter_layers(layers, pattern):
    if not pattern or pattern == '*':
        return layers
    return [l for l in layers if match_filter(l.get_name(), pattern)]

def resolve_scope(image, scope, pattern='', drawables=None):
    if scope == 'all':        layers = layers_all(image, drawables)
    elif scope == 'others':   layers = layers_other(image, drawables)
    elif scope == 'above':    layers = layers_above(image, drawables)
    elif scope == 'below':    layers = layers_below(image, drawables)
    elif scope == 'selected': layers = layers_selected(image, drawables)
    else:                     layers = layers_all(image, drawables)
    return filter_layers(layers, pattern)

def resolve_groups(image, scope, pattern='', drawables=None):
    return [l for l in resolve_scope(image, scope, pattern, drawables) if is_group(l)]

def toggle_ignore(image, drawables=None):
    layer = get_active_layer(image, drawables)
    if not layer:
        return
    image.undo_group_start()
    if layer.get_parasite('lm-ignore'):
        layer.detach_parasite('lm-ignore')
        name = layer.get_name()
        if name.startswith('[i] '):
            layer.set_name(name[4:])
    else:
        parasite = Gimp.Parasite.new('lm-ignore', Gimp.PARASITE_PERSISTENT, b'1')
        layer.attach_parasite(parasite)
        name = layer.get_name()
        if not name.startswith('[i] '):
            layer.set_name('[i] ' + name)
    image.undo_group_end()
    Gimp.displays_flush()

def clear_all_ignores(image):
    image.undo_group_start()
    for layer in get_all_layers(image):
        try:
            if layer.get_parasite('lm-ignore'):
                layer.detach_parasite('lm-ignore')
                name = layer.get_name()
                if name.startswith('[i] '):
                    layer.set_name(name[4:])
        except Exception:
            pass
    image.undo_group_end()
    Gimp.displays_flush()

def delete_selected(image):
    """Delete all currently selected layers/groups."""
    selected = image.get_selected_drawables()
    if not selected:
        return
    image.undo_group_start()
    for layer in selected:
        if isinstance(layer, Gimp.Layer):
            image.remove_layer(layer)
    image.undo_group_end()
    Gimp.displays_flush()

def add_layers(image, active, count, prefix, above, counter):
    """Add count new layers relative to active layer.
    - active is a group: add as children inside the group
    - active is a layer in a group: add as siblings in that group
    - active is a top-level layer: add at root level
    above=True inserts above/before, above=False inserts below/after.
    Returns updated counter."""
    if not active or count < 1:
        return counter

    # Determine parent group and insertion position
    parent = active.get_parent() if hasattr(active, 'get_parent') else None

    if is_group(active):
        # Insert as children inside the group
        insert_parent = active
        position = 0 if above else -1  # 0=top of group, -1=bottom
    elif parent and isinstance(parent, Gimp.GroupLayer):
        # Sibling of active layer inside its parent group
        insert_parent = parent
        siblings = list(parent.get_children())
        try:
            idx = next(i for i, c in enumerate(siblings) if c.get_id() == active.get_id())
        except StopIteration:
            idx = 0
        position = idx if above else idx + 1
    else:
        # Root level
        insert_parent = None
        top = image.get_layers()
        try:
            idx = next(i for i, l in enumerate(top) if l.get_id() == active.get_id())
        except StopIteration:
            idx = 0
        position = idx if above else idx + 1

    image.undo_group_start()
    width  = image.get_width()
    height = image.get_height()
    for n in range(count):
        name = f"{prefix} {counter}"
        counter += 1
        layer = Gimp.Layer.new(image, name, width, height,
                               Gimp.ImageType.RGBA_IMAGE, 100,
                               Gimp.LayerMode.NORMAL)
        pos = position if above else position + n
        image.insert_layer(layer, insert_parent, pos)
    image.undo_group_end()
    Gimp.displays_flush()
    return counter

def create_group_from_selected(image, name, group_counter):
    """Create a new group at the position of the topmost selected layer,
    move all selected layers into it. Returns updated counter."""
    selected = [d for d in image.get_selected_drawables() if isinstance(d, Gimp.Layer)]
    if not selected:
        return group_counter

    # Find topmost selected layer by position in flat list
    all_layers = get_all_layers(image)
    id_set = {l.get_id() for l in selected}
    top_layer = None
    for l in all_layers:
        if l.get_id() in id_set:
            top_layer = l
            break
    if not top_layer:
        return group_counter

    group_name = f"{name} {group_counter}"
    group_counter += 1

    # Determine insertion parent and position from top_layer
    parent = top_layer.get_parent() if hasattr(top_layer, 'get_parent') else None
    insert_parent = parent if (parent and isinstance(parent, Gimp.GroupLayer)) else None
    if insert_parent:
        siblings = list(insert_parent.get_children())
        try:
            pos = next(i for i, c in enumerate(siblings) if c.get_id() == top_layer.get_id())
        except StopIteration:
            pos = 0
    else:
        top_level = image.get_layers()
        try:
            pos = next(i for i, l in enumerate(top_level) if l.get_id() == top_layer.get_id())
        except StopIteration:
            pos = 0

    image.undo_group_start()
    group = Gimp.GroupLayer.new(image, group_name)
    image.insert_layer(group, insert_parent, pos)
    # Move selected layers into the group in their original order
    for layer in all_layers:
        if layer.get_id() in id_set:
            image.reorder_item(layer, group, -1)
    image.undo_group_end()
    Gimp.displays_flush()
    return group_counter

#------------------------------------------------------------------------------
# Operation dispatch
#------------------------------------------------------------------------------
OPS = {
    'layer-manager-show-all':          (lambda i, p, d: resolve_scope(i,  'all',      p, d), lambda l: l.set_visible(True)),
    'layer-manager-show-other':        (lambda i, p, d: resolve_scope(i,  'others',   p, d), lambda l: l.set_visible(True)),
    'layer-manager-show-above':        (lambda i, p, d: resolve_scope(i,  'above',    p, d), lambda l: l.set_visible(True)),
    'layer-manager-show-below':        (lambda i, p, d: resolve_scope(i,  'below',    p, d), lambda l: l.set_visible(True)),
    'layer-manager-hide-all':          (lambda i, p, d: resolve_scope(i,  'all',      p, d), lambda l: l.set_visible(False)),
    'layer-manager-hide-other':        (lambda i, p, d: resolve_scope(i,  'others',   p, d), lambda l: l.set_visible(False)),
    'layer-manager-hide-above':        (lambda i, p, d: resolve_scope(i,  'above',    p, d), lambda l: l.set_visible(False)),
    'layer-manager-hide-below':        (lambda i, p, d: resolve_scope(i,  'below',    p, d), lambda l: l.set_visible(False)),
    'layer-manager-toggle-vis-all':    (lambda i, p, d: resolve_scope(i,  'all',      p, d), lambda l: l.set_visible(not l.get_visible())),
    'layer-manager-toggle-vis-other':  (lambda i, p, d: resolve_scope(i,  'others',   p, d), lambda l: l.set_visible(not l.get_visible())),
    'layer-manager-toggle-vis-above':  (lambda i, p, d: resolve_scope(i,  'above',    p, d), lambda l: l.set_visible(not l.get_visible())),
    'layer-manager-toggle-vis-below':  (lambda i, p, d: resolve_scope(i,  'below',    p, d), lambda l: l.set_visible(not l.get_visible())),
    'layer-manager-lock-all':          (lambda i, p, d: resolve_scope(i,  'all',      p, d), lambda l: l.set_lock_alpha(True)),
    'layer-manager-lock-other':        (lambda i, p, d: resolve_scope(i,  'others',   p, d), lambda l: l.set_lock_alpha(True)),
    'layer-manager-lock-above':        (lambda i, p, d: resolve_scope(i,  'above',    p, d), lambda l: l.set_lock_alpha(True)),
    'layer-manager-lock-below':        (lambda i, p, d: resolve_scope(i,  'below',    p, d), lambda l: l.set_lock_alpha(True)),
    'layer-manager-unlock-all':        (lambda i, p, d: resolve_scope(i,  'all',      p, d), lambda l: l.set_lock_alpha(False)),
    'layer-manager-unlock-other':      (lambda i, p, d: resolve_scope(i,  'others',   p, d), lambda l: l.set_lock_alpha(False)),
    'layer-manager-unlock-above':      (lambda i, p, d: resolve_scope(i,  'above',    p, d), lambda l: l.set_lock_alpha(False)),
    'layer-manager-unlock-below':      (lambda i, p, d: resolve_scope(i,  'below',    p, d), lambda l: l.set_lock_alpha(False)),
    'layer-manager-toggle-lock-all':   (lambda i, p, d: resolve_scope(i,  'all',      p, d), lambda l: l.set_lock_alpha(not l.get_lock_alpha())),
    'layer-manager-toggle-lock-other': (lambda i, p, d: resolve_scope(i,  'others',   p, d), lambda l: l.set_lock_alpha(not l.get_lock_alpha())),
    'layer-manager-toggle-lock-above': (lambda i, p, d: resolve_scope(i,  'above',    p, d), lambda l: l.set_lock_alpha(not l.get_lock_alpha())),
    'layer-manager-toggle-lock-below': (lambda i, p, d: resolve_scope(i,  'below',    p, d), lambda l: l.set_lock_alpha(not l.get_lock_alpha())),
    'layer-manager-collapse-all':      (lambda i, p, d: resolve_groups(i, 'all',      p, d), lambda l: l.set_expanded(False)),
    'layer-manager-collapse-other':    (lambda i, p, d: resolve_groups(i, 'others',   p, d), lambda l: l.set_expanded(False)),
    'layer-manager-collapse-above':    (lambda i, p, d: resolve_groups(i, 'above',    p, d), lambda l: l.set_expanded(False)),
    'layer-manager-collapse-below':    (lambda i, p, d: resolve_groups(i, 'below',    p, d), lambda l: l.set_expanded(False)),
    'layer-manager-expand-all':        (lambda i, p, d: resolve_groups(i, 'all',      p, d), lambda l: l.set_expanded(True)),
    'layer-manager-expand-other':      (lambda i, p, d: resolve_groups(i, 'others',   p, d), lambda l: l.set_expanded(True)),
    'layer-manager-expand-above':      (lambda i, p, d: resolve_groups(i, 'above',    p, d), lambda l: l.set_expanded(True)),
    'layer-manager-expand-below':      (lambda i, p, d: resolve_groups(i, 'below',    p, d), lambda l: l.set_expanded(True)),
}

#------------------------------------------------------------------------------
# Panel builder
#------------------------------------------------------------------------------
def create_panel(drawables=None):
    state = {'last_op': None}

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.set_border_width(8)

    def get_image():
        images = Gimp.get_images()
        return images[0] if images else None

    def get_scope():
        if scope_selected.get_active(): return 'selected'
        if scope_others.get_active():   return 'others'
        if scope_above.get_active():    return 'above'
        if scope_below.get_active():    return 'below'
        return 'all'

    def get_filter():
        return filter_entry.get_text().strip()

    def on_filter_changed(widget):
        has_filter = bool(filter_entry.get_text().strip())
        for btn in scope_buttons:
            btn.set_sensitive(not has_filter)

    def run_op(op):
        state['last_op'] = op
        image = get_image()
        if image:
            active_drawables = image.get_selected_drawables() or drawables
            op(image, get_scope(), get_filter(), active_drawables)

    def on_filter_enter(widget):
        if state['last_op']:
            run_op(state['last_op'])

    def on_clear(widget):
        # Clear text only — do not re-run op
        filter_entry.set_text('')

    def on_toggle_ignore(widget):
        image = get_image()
        if image:
            active_drawables = image.get_selected_drawables() or drawables
            toggle_ignore(image, active_drawables)

    def make_btn(label, op):
        btn = Gtk.Button(label=label)
        btn.connect('clicked', lambda w: run_op(op))
        return btn

    # Filter row
    filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
    filter_entry = Gtk.Entry()
    filter_entry.set_placeholder_text('contains  text*  *text')
    filter_entry.set_tooltip_text('Empty=all  text=contains  text*=starts with  *text=ends with')
    filter_entry.connect('activate', on_filter_enter)
    filter_entry.connect('changed', on_filter_changed)
    clear_btn = Gtk.Button(label='Clear')
    clear_btn.connect('clicked', on_clear)
    filter_box.pack_start(Gtk.Label(label='Filter:'), False, False, 0)
    filter_box.pack_start(filter_entry, True, True, 0)
    filter_box.pack_start(clear_btn, False, False, 0)
    box.pack_start(filter_box, False, False, 0)
    box.pack_start(Gtk.Separator(), False, False, 2)

    # Scope
    scope_label = Gtk.Label(label='Scope:')
    scope_label.set_xalign(0)
    box.pack_start(scope_label, False, False, 0)
    scope_grid = Gtk.Grid()
    scope_grid.set_column_spacing(8)
    scope_grid.set_row_spacing(2)
    scope_all      = Gtk.RadioButton.new_with_label(None, 'All')
    scope_others   = Gtk.RadioButton.new_with_label_from_widget(scope_all, 'Others')
    scope_above    = Gtk.RadioButton.new_with_label_from_widget(scope_all, 'Above')
    scope_below    = Gtk.RadioButton.new_with_label_from_widget(scope_all, 'Below')
    scope_selected = Gtk.RadioButton.new_with_label_from_widget(scope_all, 'Selected')
    scope_buttons  = [scope_all, scope_others, scope_above, scope_below, scope_selected]
    scope_grid.attach(scope_all,      0, 0, 1, 1)
    scope_grid.attach(scope_others,   1, 0, 1, 1)
    scope_grid.attach(scope_above,    0, 1, 1, 1)
    scope_grid.attach(scope_below,    1, 1, 1, 1)
    scope_grid.attach(scope_selected, 0, 2, 2, 1)
    box.pack_start(scope_grid, False, False, 0)
    box.pack_start(Gtk.Separator(), False, False, 2)

    # Visibility
    vis_label = Gtk.Label(label='Visibility:')
    vis_label.set_xalign(0)
    box.pack_start(vis_label, False, False, 0)
    vis_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
    for lbl, fn in [
        ('Show',   lambda img, sc, pt, d: apply_op(img, resolve_scope(img, sc, pt, d), lambda l: l.set_visible(True))),
        ('Hide',   lambda img, sc, pt, d: apply_op(img, resolve_scope(img, sc, pt, d), lambda l: l.set_visible(False))),
        ('Toggle', lambda img, sc, pt, d: apply_op(img, resolve_scope(img, sc, pt, d), lambda l: l.set_visible(not l.get_visible()))),
    ]:
        vis_box.pack_start(make_btn(lbl, fn), True, True, 0)
    box.pack_start(vis_box, False, False, 0)
    box.pack_start(Gtk.Separator(), False, False, 2)

    # Lock
    lock_label = Gtk.Label(label='Lock:')
    lock_label.set_xalign(0)
    box.pack_start(lock_label, False, False, 0)
    lock_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
    for lbl, fn in [
        ('Lock',   lambda img, sc, pt, d: apply_op(img, resolve_scope(img, sc, pt, d), lambda l: l.set_lock_alpha(True))),
        ('Unlock', lambda img, sc, pt, d: apply_op(img, resolve_scope(img, sc, pt, d), lambda l: l.set_lock_alpha(False))),
        ('Toggle', lambda img, sc, pt, d: apply_op(img, resolve_scope(img, sc, pt, d), lambda l: l.set_lock_alpha(not l.get_lock_alpha()))),
    ]:
        lock_box.pack_start(make_btn(lbl, fn), True, True, 0)
    box.pack_start(lock_box, False, False, 0)
    box.pack_start(Gtk.Separator(), False, False, 2)

    # Groups
    grp_label = Gtk.Label(label='Groups:')
    grp_label.set_xalign(0)
    box.pack_start(grp_label, False, False, 0)
    grp_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
    for lbl, fn in [
        ('Collapse', lambda img, sc, pt, d: apply_op(img, resolve_groups(img, sc, pt, d), lambda l: l.set_expanded(False))),
        ('Expand',   lambda img, sc, pt, d: apply_op(img, resolve_groups(img, sc, pt, d), lambda l: l.set_expanded(True))),
    ]:
        grp_box.pack_start(make_btn(lbl, fn), True, True, 0)
    box.pack_start(grp_box, False, False, 0)
    box.pack_start(Gtk.Separator(), False, False, 2)

    # Add Layers
    layer_counter = [1]
    group_counter = [1]

    def on_add_layers(above):
        image = get_image()
        if not image:
            return
        active_drawables = image.get_selected_drawables() or drawables
        active = get_active_layer(image, active_drawables)
        count  = int(add_count_spin.get_value())
        prefix = add_prefix_entry.get_text().strip() or 'new layer'
        layer_counter[0] = add_layers(image, active, count, prefix, above, layer_counter[0])

    def on_context_changed(image=None):
        """Update Add buttons based on whether active is a group or layer."""
        img = get_image()
        if not img:
            return
        active_drawables = img.get_selected_drawables() or drawables
        active = get_active_layer(img, active_drawables)
        if active and is_group(active):
            add_above_btn.hide()
            add_below_btn.hide()
            add_in_btn.show()
            grp_row.hide()
        else:
            add_above_btn.show()
            add_below_btn.show()
            add_in_btn.hide()
            grp_row.show()

    def on_create_group(widget):
        image = get_image()
        if not image:
            return
        prefix = grp_prefix_entry.get_text().strip() or 'New Group'
        group_counter[0] = create_group_from_selected(image, prefix, group_counter[0])

    add_label = Gtk.Label(label='Add Layers:')
    add_label.set_xalign(0)
    box.pack_start(add_label, False, False, 0)

    add_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
    add_prefix_entry = Gtk.Entry()
    add_prefix_entry.set_text('new layer')
    add_prefix_entry.set_tooltip_text('Layer name prefix')
    add_prefix_entry.set_width_chars(12)
    add_count_spin = Gtk.SpinButton()
    add_count_spin.set_adjustment(Gtk.Adjustment(value=3, lower=1, upper=99, step_increment=1))
    add_count_spin.set_width_chars(3)
    add_above_btn = Gtk.Button(label='Above')
    add_above_btn.connect('clicked', lambda w: on_add_layers(True))
    add_below_btn = Gtk.Button(label='Below')
    add_below_btn.connect('clicked', lambda w: on_add_layers(False))
    add_in_btn = Gtk.Button(label='In Group')
    add_in_btn.connect('clicked', lambda w: on_add_layers(True))  # above=True = top of group children
    add_row.pack_start(add_prefix_entry, True,  True,  0)
    add_row.pack_start(add_count_spin,   False, False, 0)
    add_row.pack_start(add_above_btn,    False, False, 0)
    add_row.pack_start(add_below_btn,    False, False, 0)
    add_row.pack_start(add_in_btn,       False, False, 0)
    box.pack_start(add_row, False, False, 0)

    # Create Group row
    grp_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
    grp_prefix_entry = Gtk.Entry()
    grp_prefix_entry.set_text('New Group')
    grp_prefix_entry.set_tooltip_text('Group name prefix')
    grp_prefix_entry.set_width_chars(12)
    grp_prefix_entry.connect('activate', on_create_group)
    create_grp_btn = Gtk.Button(label='Create Group')
    create_grp_btn.set_tooltip_text('Group selected layers into a new group')
    create_grp_btn.connect('clicked', on_create_group)
    grp_row.pack_start(grp_prefix_entry, True,  True,  0)
    grp_row.pack_start(create_grp_btn,   False, False, 0)
    box.pack_start(grp_row, False, False, 0)
    box.pack_start(Gtk.Separator(), False, False, 2)

    # Connect a timer to poll active layer type for button context switching
    def poll_context():
        on_context_changed()
        return True  # keep repeating
    GLib.timeout_add(500, poll_context)

    # Ignore
    ignore_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
    ignore_btn = Gtk.Button(label='Toggle Ignore on Active')
    ignore_btn.set_tooltip_text('Mark/unmark active layer to be skipped by all operations')
    ignore_btn.connect('clicked', on_toggle_ignore)
    clear_ignore_btn = Gtk.Button(label='Clear All Ignores')
    clear_ignore_btn.set_tooltip_text('Remove ignore mark from all layers')
    clear_ignore_btn.connect('clicked', lambda w: (lambda img: clear_all_ignores(img) if img else None)(get_image()))
    ignore_box.pack_start(ignore_btn, True, True, 0)
    ignore_box.pack_start(clear_ignore_btn, True, True, 0)
    box.pack_start(ignore_box, False, False, 0)
    box.pack_start(Gtk.Separator(), False, False, 2)

    # Delete
    delete_btn = Gtk.Button(label='Delete Selected Layers/Groups')
    delete_btn.set_tooltip_text('Delete all currently selected layers and groups')
    delete_btn.connect('clicked', lambda w: (lambda img: delete_selected(img) if img else None)(get_image()))
    box.pack_start(delete_btn, False, False, 0)

    box.show_all()
    return box

#------------------------------------------------------------------------------
# Procedure list
#------------------------------------------------------------------------------
PROCEDURES = [
    ('layer-manager-show-all',          '<Image>/Filters/Layer Manager/Visibility/', 'Show All'),
    ('layer-manager-show-other',        '<Image>/Filters/Layer Manager/Visibility/', 'Show Others'),
    ('layer-manager-show-above',        '<Image>/Filters/Layer Manager/Visibility/', 'Show Above'),
    ('layer-manager-show-below',        '<Image>/Filters/Layer Manager/Visibility/', 'Show Below'),
    ('layer-manager-hide-all',          '<Image>/Filters/Layer Manager/Visibility/', 'Hide All'),
    ('layer-manager-hide-other',        '<Image>/Filters/Layer Manager/Visibility/', 'Hide Others'),
    ('layer-manager-hide-above',        '<Image>/Filters/Layer Manager/Visibility/', 'Hide Above'),
    ('layer-manager-hide-below',        '<Image>/Filters/Layer Manager/Visibility/', 'Hide Below'),
    ('layer-manager-toggle-vis-all',    '<Image>/Filters/Layer Manager/Visibility/', 'Toggle All'),
    ('layer-manager-toggle-vis-other',  '<Image>/Filters/Layer Manager/Visibility/', 'Toggle Others'),
    ('layer-manager-toggle-vis-above',  '<Image>/Filters/Layer Manager/Visibility/', 'Toggle Above'),
    ('layer-manager-toggle-vis-below',  '<Image>/Filters/Layer Manager/Visibility/', 'Toggle Below'),
    ('layer-manager-lock-all',          '<Image>/Filters/Layer Manager/Lock/',       'Lock All'),
    ('layer-manager-lock-other',        '<Image>/Filters/Layer Manager/Lock/',       'Lock Others'),
    ('layer-manager-lock-above',        '<Image>/Filters/Layer Manager/Lock/',       'Lock Above'),
    ('layer-manager-lock-below',        '<Image>/Filters/Layer Manager/Lock/',       'Lock Below'),
    ('layer-manager-unlock-all',        '<Image>/Filters/Layer Manager/Lock/',       'Unlock All'),
    ('layer-manager-unlock-other',      '<Image>/Filters/Layer Manager/Lock/',       'Unlock Others'),
    ('layer-manager-unlock-above',      '<Image>/Filters/Layer Manager/Lock/',       'Unlock Above'),
    ('layer-manager-unlock-below',      '<Image>/Filters/Layer Manager/Lock/',       'Unlock Below'),
    ('layer-manager-toggle-lock-all',   '<Image>/Filters/Layer Manager/Lock/',       'Toggle All'),
    ('layer-manager-toggle-lock-other', '<Image>/Filters/Layer Manager/Lock/',       'Toggle Others'),
    ('layer-manager-toggle-lock-above', '<Image>/Filters/Layer Manager/Lock/',       'Toggle Above'),
    ('layer-manager-toggle-lock-below', '<Image>/Filters/Layer Manager/Lock/',       'Toggle Below'),
    ('layer-manager-collapse-all',      '<Image>/Filters/Layer Manager/Groups/',     'Collapse All'),
    ('layer-manager-collapse-other',    '<Image>/Filters/Layer Manager/Groups/',     'Collapse Others'),
    ('layer-manager-collapse-above',    '<Image>/Filters/Layer Manager/Groups/',     'Collapse Above'),
    ('layer-manager-collapse-below',    '<Image>/Filters/Layer Manager/Groups/',     'Collapse Below'),
    ('layer-manager-expand-all',        '<Image>/Filters/Layer Manager/Groups/',     'Expand All'),
    ('layer-manager-expand-other',      '<Image>/Filters/Layer Manager/Groups/',     'Expand Others'),
    ('layer-manager-expand-above',      '<Image>/Filters/Layer Manager/Groups/',     'Expand Above'),
    ('layer-manager-expand-below',      '<Image>/Filters/Layer Manager/Groups/',     'Expand Below'),
    ('layer-manager-toggle-ignore',     '<Image>/Filters/Layer Manager/',            'Toggle Ignore on Active'),
    ('layer-manager-clear-ignores',     '<Image>/Filters/Layer Manager/',            'Clear All Ignores'),
    ('layer-manager-dialog',            '<Image>/Filters/Layer Manager/',            'Open Panel...'),
    ('layer-manager-open',              '<Layers>/[Layers]/',                        'Open Layer Manager'),
]

#------------------------------------------------------------------------------
# Plugin class
#------------------------------------------------------------------------------
class MapsEdgeLayerManager(Gimp.PlugIn):
    __gtype_name__ = 'MapsEdgeLayerManager'

    def do_set_i18n(self, name):
        return False

    def do_query_procedures(self):
        return [p[0] for p in PROCEDURES]

    def do_create_procedure(self, name):
        defn = next(p for p in PROCEDURES if p[0] == name)
        _, menu_path, label = defn
        procedure = Gimp.ImageProcedure.new(
            self, name, Gimp.PDBProcType.PLUGIN,
            self.run, None)
        procedure.set_image_types('*')
        procedure.set_sensitivity_mask(
            Gimp.ProcedureSensitivityMask.DRAWABLE |
            Gimp.ProcedureSensitivityMask.NO_DRAWABLES)
        procedure.set_menu_label(label)
        procedure.add_menu_path(menu_path)
        procedure.set_documentation(label, label, name)
        procedure.set_attribution('Maps Edge Creative', 'Maps Edge Creative', '2026')
        return procedure

    def run(self, procedure, run_mode, image, drawables, config, run_data):
        name = procedure.get_name()
        active_drawables = list(drawables) if drawables else []
        if name in ('layer-manager-dialog', 'layer-manager-open'):
            # Singleton: find existing dialog by role and present it
            for win in Gtk.Window.list_toplevels():
                if win.get_role() == 'layer-manager' and win.get_visible():
                    win.present()
                    return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())
            GimpUi.init('layer-manager')
            dialog = GimpUi.Dialog(title='Layer Manager', role='layer-manager',
                                   use_header_bar=False)
            dialog.add_button('_Close', Gtk.ResponseType.CLOSE)
            panel = create_panel(active_drawables)
            dialog.get_content_area().pack_start(panel, True, True, 0)
            dialog.show_all()
            dialog.run()
            dialog.destroy()
        elif name == 'layer-manager-toggle-ignore':
            toggle_ignore(image, active_drawables)
        elif name == 'layer-manager-clear-ignores':
            clear_all_ignores(image)
        elif name in OPS:
            layer_fn, op = OPS[name]
            apply_op(image, layer_fn(image, '', active_drawables), op)
        return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())

Gimp.main(MapsEdgeLayerManager.__gtype__, sys.argv)
