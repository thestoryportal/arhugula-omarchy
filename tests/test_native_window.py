import unittest


class NativeWindowTests(unittest.TestCase):
    def test_hyprland_eval_ack_is_ok_not_lua_print_output(self):
        from ops.orchestration.native_window import NativeWindow, WindowCapability
        window=NativeWindow(WindowCapability('0xabc','stable',10,'100',11,'101'),'.')
        window.check=lambda:None
        window.command=lambda argv:'ok\n'
        window.type('literal')
        window.submit()
    def test_literal_prompt_keys_are_window_bound_without_clipboard_or_focus(self):
        from ops.orchestration.native_window import key_events, input_program
        self.assertEqual(key_events('A1_/: '), [
            ('SHIFT','a'),('','1'),('SHIFT','minus'),('','slash'),
            ('SHIFT','semicolon'),('','space')])
        program=input_program('0xabc', 'A1_/: ')
        self.assertIn('address:0xabc',program)
        self.assertNotIn('focus(',program)
        self.assertNotIn('clipboard',program)

    def test_unsupported_text_is_refused_before_any_dispatch(self):
        from ops.orchestration.native_window import input_program
        for text in ('line\nbreak', 'snowman \u2603', '\x00'):
            with self.assertRaises(ValueError):input_program('0xabc',text)
        with self.assertRaises(ValueError):input_program("0xabc');os.execute('bad')",'safe')

    def test_window_and_pid_reuse_refuse_target_capability(self):
        from ops.orchestration.native_window import WindowCapability
        cap=WindowCapability('0xabc','stable',10,'100',11,'101')
        client={'address':'0xabc','stableId':'stable','pid':10,'mapped':True,'acceptsInput':True}
        processes={10:('100',1),11:('101',10)}
        self.assertEqual(cap.parse([client],processes).address,'0xabc')
        for changed in ({**client,'stableId':'reused'},{**client,'pid':12}):
            with self.assertRaises(ValueError):cap.parse([changed],processes)
        with self.assertRaises(ValueError):cap.parse([client],{10:('999',1),11:('101',10)})
        with self.assertRaises(ValueError):cap.parse([client],{10:('100',1),11:('101',99)})

    def test_keyboard_layout_and_caps_must_match_literal_delivery(self):
        from ops.orchestration.native_window import require_us_keyboard
        good={'main':True,'active_keymap':'English (US)','capsLock':False}
        require_us_keyboard([good])
        for rows in ([],[{**good,'capsLock':True}],[{**good,'active_keymap':'German'}]):
            with self.assertRaises(ValueError):require_us_keyboard(rows)
