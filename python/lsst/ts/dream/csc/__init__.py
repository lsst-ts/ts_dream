# This file is part of ts_dream.
#
# Developed for the Vera C. Rubin Observatory Telescope and Site Systems.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import typing

# See https://confluence.lsstcorp.org/display/LTS/Enabling+Mypy+in+Pytest for
# why this construction is needed.
if typing.TYPE_CHECKING:
    __version__ = "?"
else:
    try:
        from .version import __version__
    except ImportError:
        __version__ = "?"

from .config_schema import CONFIG_SCHEMA
from .dream_csc import *
from .mock import *
