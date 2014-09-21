# -*- coding: utf-8 -*-

"""
Handler class for processing built-in commands and delegating messages.
"""
from __future__ import absolute_import, division, unicode_literals

import re
import logging
import shlex
import random
from inspect import getmembers, ismethod

from sevabot.bot import modules
from sevabot.utils import ensure_unicode

logger = logging.getLogger('sevabot')


class CommandHandler:
    """A handler for processing built-in commands and delegating messages to reloadable modules.
    """

    def __init__(self, sevabot, acl = None):
        self.sevabot = sevabot
        self.calls = {}
        self.cache_builtins()
        self.acl = acl

    def cache_builtins(self):
        """Scan all built-in commands defined in this handler.
        """

        def wanted(member):
            return ismethod(member) and member.__name__.startswith('builtin_')

        self.builtins = {}
        for member in getmembers(self, wanted):
            command_name = re.split('^builtin_', member[0])[1]
            self.builtins[command_name] = member[1]
            logger.info('Built-in command {} is available.'.format(command_name))

    def handle(self, msg, status):
        """Handle command messages.
        """

        # If you are talking to yourself when testing
        # Ignore non-sent messages (you get both SENDING and SENT events)
        if status == "SENDING":
            return

        # Some Skype clients (iPad?)
        # double reply to the chat messages with some sort of ACK by
        # echoing them back
        # and we need to ignore them as they are not real chat messages
        # and not even displayed in chat UI
        if status == "READ":
            return


        # Check all stateful handlers
        for handler in modules.get_message_handlers():
            processed = handler(msg, status)
            if processed:
                # Handler processed the message
                return

        # We need utf-8 for shlex
        body = ensure_unicode(msg.Body).encode('utf-8')

        logger.debug(u"Processing message, body %s" % msg.Body)

        # shlex dies on unicode on OSX with null bytes all over the string
        try:
            words = shlex.split(body, comments=False, posix=True)
        except ValueError:
            # ValueError: No closing quotation
            return

        words = [word.decode('utf-8') for word in words]

        if len(words) < 1:
            return

        command_name = words[0]
        command_args = words[1:]

        # Beyond this point we process script commands only
        if not command_name.startswith('!'):
            return

        if self.acl and not self.acl.is_allowed(msg.Sender.Handle):
            msg.Chat.SendMessage(
                'You are in non of the main group chats, you cannot give me commands :p\n' +
                'go and find another BOT [or ask for inclusion to the main chats] (emo)'
            )
            logger.debug(msg.Sender.Handle)
            return

        command_name = command_name[1:]

        script_module = modules.get_script_module(command_name)

        if command_name in self.builtins:
            # Execute a built-in command
            logger.debug('Executing built-in command {}: {}'.format(command_name, command_args))
            self.builtins[command_name](command_args, msg, status)
        elif script_module:

            # Execute a module asynchronously
            def callback(output):
                msg.Chat.SendMessage(output)

            script_module.run(msg, command_args, callback)
        else:
            cmds = []
            [cmds.append(i) for i in modules._modules.keys() if i.startswith(command_name[0])]
            if not cmds:
                cmds.append(random.choice(modules._modules.keys()))
            message = "%s, I don't know about command: !%s, maybe you mean another one: %s" % (
                msg.Sender.Handle, command_name, cmds)
            msg.Chat.SendMessage(message)

    def builtin_reload(self, args, msg, status):
        """Reload command modules.
        """

        from sevabot.frontend.main import get_settings

        if msg.FromHandle not in get_settings().ADMINS:
            logger.warning("Access denied for %s" % (msg.FromHandle))
            return

        commands = modules.load_modules(self.sevabot)
        msg.Chat.SendMessage('Available commands: %s' % ', '.join(commands))
