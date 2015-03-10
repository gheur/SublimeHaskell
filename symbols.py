# -*- coding: UTF-8 -*-

import threading
import sublime
import os.path

if int(sublime.version()) < 3000:
    from sublime_haskell_common import *
    from haskell_docs import haskell_docs
else:
    from SublimeHaskell.sublime_haskell_common import *
    from SublimeHaskell.haskell_docs import haskell_docs
    from functools import reduce

class Position(object):
    def __init__(self, line, column):
        self.line = line
        self.column = column

    def __str__(self):
        return self.to_string()

    def to_string(self):
        if self.column is None:
            return str(self.line)
        return ':'.join([str(self.line), str(self.column)])

class Location(object):
    """
    Location in file at line
    """
    def __init__(self, filename, project = None):
        if not project and filename:
            project = get_cabal_project_dir_of_file(filename)
        self.project = project
        self.filename = filename

    def __str__(self):
        return self.to_string()

    def to_string(self):
        return self.filename

    def is_null(self):
        return self.project is None and self.filename is None

def source_location(loc, pos):
    """ Returns filename:line:column """
    if not pos:
        return str(loc)
    return ':'.join([str(loc), str(pos)])

class Package(object):
    def __init__(self, name, version = None):
        self.name = name
        self.version = version

    def package_id(self):
        return '{0}-{1}'.format(self.name, self.version) if self.version is not None else self.name

def parse_package(package_id):
    if package_id is None:
        return None
    m = re.match('([\w\-]+)\-([\d\.]+)', package_id)
    if m:
        (name, version) = m.groups()
        return Package(name, version)
    m = re.match('([\w\-]+)', package_id)
    if m:
        (name, ) = m.groups()
        return Package(name)
    return None

class InstalledLocation(object):
    """
    Module location in cabal
    """
    def __init__(self, package, cabal = None):
        if not cabal:
            cabal = 'cabal'
        self.package = package
        self.cabal = cabal

    def __str__(self):
        return self.to_string()

    def to_string(self):
        return '{0} in {1}'.format(self.package.package_id(), self.cabal)

    def is_null(self):
        return self.package is None

class OtherLocation(object):
    """
    Other module location
    """
    def __init__(self, source):
        self.source = source

    def __str__(self):
        return self.to_string()

    def to_string(self):
        return (self.source or "")

    def is_null(self):
        return self.source is None

def location_package_name(loc):
    if type(loc) == InstalledLocation and loc.package:
        return loc.package.name
    return None

def location_project(loc):
    if type(loc) == Location and loc.project:
        return loc.project
    return None

def location_cabal(loc):
    if type(loc) == InstalledLocation:
        return loc.cabal
    return None

class Symbol(object):
    """
    Haskell symbol: module, function, data, class etc.
    """
    def __init__(self, symbol_type, name, docs = None, location = None, defined = None, position = None, module = None):
        self.what = symbol_type
        self.name = name
        self.defined = defined
        self.position = position
        self.module = module
        self.docs = docs
        self.location = location

        self.tags = {}

    def full_name(self):
        return self.module.name + '.' + self.name

    def by_source(self):
        return type(self.location) == Location

    def by_cabal(self):
        return type(self.location) == InstalledLocation

    def by_hayoo(self):
        return type(self.location) == OtherLocation

    def has_source_location(self):
        loc = self.defined_module().location
        return type(loc) == Location and self.position is not None

    def other_location(self):
        loc = self.defined_module().location
        return type(loc) == OtherLocation

    def get_source_location(self):
        loc = self.defined_module().location
        if type(loc) == Location:
            return source_location(loc, self.position)
        return None

    def defined_module(self):
        return self.defined or self.module

    def defined_location(self):
        return self.defined_module().location

class Import(object):
    """
    Haskell import of module
    """
    def __init__(self, module_name, is_qualified = False, import_as = None, position = None, location = None):
        self.module = module_name
        self.is_qualified = is_qualified
        self.import_as = import_as
        self.position = position
        self.location = location

    def dump(self):
        return self.__dict__

def module_location(filename):
    return Location(filename)

class Module(Symbol):
    """
    Haskell module symbol
    """
    def __init__(self, module_name, exports = None, imports = [], declarations = {}, location = None, cabal = None, last_inspection_time = 0):
        super(Module, self).__init__('module', module_name, None, location)
        # List of strings
        if exports is not None:
            self.exports = exports[:]
        # Dictionary from module name to Import object
        self.imports = imports[:]
        for i in self.imports:
            i.location = self.location
        # Dictionary from name to Symbol
        self.declarations = declarations.copy()
        for d in self.declarations.values():
            d.location = self.location

        for decl in self.declarations.values():
            decl.module = self

        # Cabal path or 'cabal'
        self.cabal = cabal

        # Time as from time.time()
        self.last_inspection_time = last_inspection_time

    def add_declaration(self, new_declaration):
        if not new_declaration.module:
            new_declaration.module = self
        new_declaration.location = self.location
        if new_declaration.module != self:
            raise RuntimeError("Adding declaration to other module")
        self.declarations[new_declaration.name] = new_declaration

    def unalias(self, module_alias):
        """
        Unalias module import if any
        Returns list of unaliased modules
        """
        return [i.module for i in self.imports if i.import_as == module_alias]

class Declaration(Symbol):
    def __init__(self, name, decl_type = 'declaration', docs = None, location = None, imported = [], defined = None, position = None, module = None):
        super(Declaration, self).__init__(decl_type, name, docs, location, defined, position, module)
        self.imported = imported[:]

    def make_qualified(self):
        self.name = self.qualified_name()

    def module_name(self):
        if self.imported:
            return self.imported[0].module
        return self.module.name

    def imported_names(self):
        if self.imported:
            return sorted(list(set([i.module for i in self.imported])))
        return [self.module.name]

    def imported_from_name(self):
        return self.imported_names()[0]

    def suggest(self):
        """ Returns suggestion for this declaration """
        return ('{0}\t{1}'.format(self.name, self.imported_from_name()), self.name)

    def brief(self):
        return self.name

    def qualified_name(self):
        return '.'.join([self.module_name(), self.name])

    def detailed(self):
        """ Detailed info for use in Symbol Info command """
        info = [
            self.brief(),
            '',
            'Imported from {0}'.format(', '.join(self.imported_names()))]

        if self.docs:
            info.extend(['', self.docs])

        info.append('')

        if self.has_source_location():
            if self.location.project:
                info.append('Project: {0}'.format(self.location.project))
        elif self.other_location():
            pass
        else:
            info.append('Installed in: {0}'.format(self.defined_location().cabal))
            info.append('Package: {0}'.format(self.defined_location().package.package_id()))

        if self.has_source_location():
            info.append('Defined at: {0}'.format(self.get_source_location()))
        else:
            info.append('Defined in: {0}'.format(self.defined_module().name))

        return '\n'.join(info)

def wrap_operator(name):
    if re.match(r"[\w']+", name):
        return name
    return "({0})".format(name)

class Function(Declaration):
    """
    Haskell function declaration
    """
    def __init__(self, name, function_type, docs = None, location = None, imported = [], defined = None, position = None, module = None):
        super(Function, self).__init__(name, 'function', docs, location, imported, defined, position, module)
        self.type = function_type

    def suggest(self):
        return (u'{0} :: {1}\t{2}'.format(wrap_operator(self.name), self.type, self.imported_from_name()), self.name)

    def brief(self):
        return u'{0} :: {1}'.format(wrap_operator(self.name), self.type if self.type else u'?')

class TypeBase(Declaration):
    """
    Haskell type, data or class
    """
    def __init__(self, name, decl_type, context, args, definition = None, docs = None, location = None, imported = [], defined = None, position = None, module = None):
        super(TypeBase, self).__init__(name, decl_type, docs, location, imported, defined, position, module)
        self.context = context
        self.args = args
        self.definition = definition

    def suggest(self):
        return (u'{0} {1}\t{2}'.format(self.name, ' '.join(self.args), self.imported_from_name()), self.name)

    def brief(self):
        brief_parts = [self.what]
        if self.context:
            if len(self.context) == 1:
                brief_parts.append(u'{0} =>'.format(self.context[0]))
            else:
                brief_parts.append(u'({0}) =>'.format(', '.join(self.context)))
        brief_parts.append(self.name)
        if self.args:
            brief_parts.append(u' '.join(self.args))
        if self.definition:
            brief_parts.append(u' = {0}'.format(self.definition))
        return u' '.join(brief_parts)

class Type(TypeBase):
    """
    Haskell type synonym
    """
    def __init__(self, name, context, args, definition = None, docs = None, location = None, imported = [], defined = None, position = None, module = None):
        super(Type, self).__init__(name, 'type', context, args, definition, docs, location, imported, defined, position, module)

class Newtype(TypeBase):
    """
    Haskell newtype synonym
    """
    def __init__(self, name, context, args, definition = None, docs = None, location = None, imported = [], defined = None, position = None, module = None):
        super(Newtype, self).__init__(name, 'newtype', context, args, definition, docs, location, imported, defined, position, module)

class Data(TypeBase):
    """
    Haskell data declaration
    """
    def __init__(self, name, context, args, definition = None, docs = None, location = None, imported = [], defined = None, position = None, module = None):
        super(Data, self).__init__(name, 'data', context, args, definition, docs, location, imported, defined, position, module)

class Class(TypeBase):
    """
    Haskell class declaration
    """
    def __init__(self, name, context, args, definition = None, docs = None, location = None, imported = [], defined = None, position = None, module = None):
        super(Class, self).__init__(name, 'class', context, args, None, docs, location, imported, defined, position, module)

def update_with(l, r, default_value, f):
    """
    unionWith for Python, but modifying first dictionary instead of returning result
    """
    for k, v in r.items():
        if k not in l:
            l[k] = default_value[:]
        l[k] = f(l[k], v)
    return l

def same_module(l, r):
    """
    Returns true if l is same module as r, which is when module name is equal
    and modules defined in one file, in same cabal-dev sandbox or in cabal
    """
    same_cabal = l.cabal and r.cabal and (l.cabal == r.cabal)
    same_filename = l.location and r.location and (l.location.filename == r.location.filename)
    nowhere = (not l.cabal) and (not l.location) and (not r.cabal) and (not r.location)
    return l.name == r.name and (same_cabal or same_filename or nowhere)

def same_declaration(l, r):
    """
    Returns true if l is same declaration as r
    """
    same_mod = l.module and r.module and same_module(l.module, r.module)
    nowhere = (not l.module) and (not r.module)
    return l.name == r.name and (same_mod or nowhere)

def is_within_project(module, project):
    """
    Returns whether module defined within project specified
    """
    if module.location:
        return module.location.project == project
    return False

def is_within_cabal(module, cabal = None):
    """
    Returns whether module loaded from cabal specified
    If cabal is None, used current cabal
    """
    if not cabal:
        cabal = current_cabal()
    return module.cabal == cabal

def is_by_sources(module):
    """
    Returns whether module defined by sources
    """
    return module.location is not None

def flatten(lsts):
    return reduce(lambda l, r: list(l) + list(r), lsts)


class CabalPackage(object):
    def __init__(self, name, synopsis = None, version = None, installed = [], homepage = None, license = None):
        self.name = name
        self.synopsis = synopsis
        self.default_version = version
        self.installed_versions = installed[:]
        self.homepage = homepage
        self.license = license

    def brief(self):
        return self.name

    def detailed(self):
        info = []
        info.append(self.brief())
        info.append('')
        if self.synopsis:
            info.append(self.synopsis)
            info.append('')
        if self.default_version:
            info.append('Last version: ' + self.default_version)
        if self.installed_versions:
            info.append('Installed versions: ' + ", ".join(self.installed_versions))
        if self.homepage:
            info.append('Homepage: ' + self.homepage)
        if self.license:
            info.append('License: ' + self.license)

        return '\n'.join(info)

class Corrector(object):
    def __init__(self, start, end, contents):
        self.start = start
        self.end = end
        self.contents = contents

    def to_region(self, view):
        return sublime.Region(view.text_point(self.start.line, self.start.column), view.text_point(self.end.line, self.end.column))

class Correction(object):
    def __init__(self, file, type, description, message, solution, corrector):
        self.file = file
        self.type = type
        self.description = description
        self.message = message
        self.solution = solution
        self.corrector = corrector

    def to_region(self, view):
        return self.corrector.to_region(view)

def mark_corrections(views, corrs):
    for view in views:
        if view.file_name() is None:
            continue
        corrs_ = [corr for corr in corrs if os.path.samefile(corr.file, view.file_name())]
        view.add_regions('autofix', [corr.to_region(view) for corr in corrs_], 'entity.name.function', 'dot', 0)
