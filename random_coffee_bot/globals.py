class JobContext:
    def __init__(self):
        self.bot = None
        self.dispatcher = None
        self.session_maker = None

    def set_context(self, bot, dispatcher, session_maker):
        self.bot = bot
        self.dispatcher = dispatcher
        self.session_maker = session_maker

    def get_context(self):
        return self.bot, self.dispatcher, self.session_maker


job_context = JobContext()