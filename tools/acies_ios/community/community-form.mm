#import "community-form.h"
#import "community-keychain.h"

@implementation AciesCommunityForm {
    AciesCommunityClient* _client;
    NSURL* _origin;
    NSDictionary<NSString*, NSString*>* _saved;
    AciesCommunityReady _ready;
    UISegmentedControl* _mode;
    UITextField* _username;
    UITextField* _password;
    UITextField* _invite;
    UIButton* _submit;
    UIButton* _continueButton;
    UILabel* _message;
    UIActivityIndicatorView* _busy;
}

- (nullable instancetype)initWithOrigin:(NSURL*)origin allowLoopbackHTTP:(BOOL)allow
                                  ready:(AciesCommunityReady)ready {
    AciesCommunityClient* client = [[AciesCommunityClient alloc] initWithOrigin:origin
                                                             allowLoopbackHTTP:allow];
    if (!client) return nil;
    self = [super initWithNibName:nil bundle:nil];
    if (self) {
        _client = client;
        _origin = [origin copy];
        if (!allow) _saved = AciesLoadCommunityKeychain(origin);
        _ready = [ready copy];
    }
    return self;
}

- (UITextField*)field:(NSString*)label textContentType:(UITextContentType)content {
    UITextField* field = [UITextField new];
    field.placeholder = label;
    field.accessibilityLabel = label;
    field.textContentType = content;
    field.autocapitalizationType = UITextAutocapitalizationTypeNone;
    field.autocorrectionType = UITextAutocorrectionTypeNo;
    field.borderStyle = UITextBorderStyleRoundedRect;
    field.font = [UIFont preferredFontForTextStyle:UIFontTextStyleBody];
    field.adjustsFontForContentSizeCategory = YES;
    [field.heightAnchor constraintGreaterThanOrEqualToConstant:44].active = YES;
    return field;
}

- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = UIColor.systemBackgroundColor;
    UIScrollView* scroll = [UIScrollView new];
    scroll.keyboardDismissMode = UIScrollViewKeyboardDismissModeInteractive;
    scroll.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:scroll];

    UILabel* title = [UILabel new];
    title.text = @"ACIES account";
    title.font = [UIFont preferredFontForTextStyle:UIFontTextStyleTitle1];
    title.adjustsFontForContentSizeCategory = YES;
    title.accessibilityTraits |= UIAccessibilityTraitHeader;

    _mode = [[UISegmentedControl alloc] initWithItems:@[@"Sign in", @"Sign up"]];
    _mode.selectedSegmentIndex = 0;
    [_mode addTarget:self action:@selector(updateMode) forControlEvents:UIControlEventValueChanged];

    _username = [self field:@"Username" textContentType:UITextContentTypeUsername];
    _password = [self field:@"Password" textContentType:UITextContentTypePassword];
    _password.secureTextEntry = YES;
    _invite = [self field:@"Invitation code, if required" textContentType:UITextContentTypeOneTimeCode];

    _submit = [UIButton buttonWithConfiguration:UIButtonConfiguration.filledButtonConfiguration
                                    primaryAction:nil];
    [_submit addTarget:self action:@selector(submit) forControlEvents:UIControlEventTouchUpInside];
    [_submit.heightAnchor constraintGreaterThanOrEqualToConstant:44].active = YES;

    _continueButton = [UIButton buttonWithConfiguration:UIButtonConfiguration.tintedButtonConfiguration
                                           primaryAction:nil];
    _continueButton.hidden = !_saved;
    UIButtonConfiguration* continueConfig = _continueButton.configuration;
    continueConfig.title = _saved ? [@"Continue as " stringByAppendingString:_saved[@"user"]] : @"Continue";
    _continueButton.configuration = continueConfig;
    [_continueButton addTarget:self action:@selector(continueSaved) forControlEvents:UIControlEventTouchUpInside];
    [_continueButton.heightAnchor constraintGreaterThanOrEqualToConstant:44].active = YES;

    _message = [UILabel new];
    _message.font = [UIFont preferredFontForTextStyle:UIFontTextStyleFootnote];
    _message.adjustsFontForContentSizeCategory = YES;
    _message.numberOfLines = 0;
    _message.textColor = UIColor.systemRedColor;
    _busy = [[UIActivityIndicatorView alloc] initWithActivityIndicatorStyle:UIActivityIndicatorViewStyleMedium];
    _busy.hidesWhenStopped = YES;

    auto form = [[UIStackView alloc] initWithArrangedSubviews:@[
        title, _continueButton, _mode, _username, _password, _invite, _submit, _busy, _message
    ]];
    form.translatesAutoresizingMaskIntoConstraints = NO;
    form.axis = UILayoutConstraintAxisVertical;
    form.spacing = 12;
    [scroll addSubview:form];

    UILayoutGuide* safe = self.view.safeAreaLayoutGuide;
    UILayoutGuide* area = scroll.frameLayoutGuide;
    UILayoutGuide* content = scroll.contentLayoutGuide;
    NSLayoutConstraint* idealWidth = [form.widthAnchor constraintEqualToAnchor:area.widthAnchor constant:-48];
    idealWidth.priority = UILayoutPriorityDefaultHigh;
    [NSLayoutConstraint activateConstraints:@[
        [scroll.topAnchor constraintEqualToAnchor:safe.topAnchor],
        [scroll.bottomAnchor constraintEqualToAnchor:self.view.keyboardLayoutGuide.topAnchor],
        [scroll.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor],
        [scroll.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor],
        [form.topAnchor constraintEqualToAnchor:content.topAnchor constant:20],
        [form.bottomAnchor constraintEqualToAnchor:content.bottomAnchor constant:-24],
        [form.leadingAnchor constraintGreaterThanOrEqualToAnchor:content.leadingAnchor constant:24],
        [form.trailingAnchor constraintLessThanOrEqualToAnchor:content.trailingAnchor constant:-24],
        [content.widthAnchor constraintEqualToAnchor:area.widthAnchor],
        [form.centerXAnchor constraintEqualToAnchor:area.centerXAnchor],
        [form.widthAnchor constraintLessThanOrEqualToConstant:440],
        idealWidth
    ]];
    [self updateMode];
}

- (void)updateMode {
    const BOOL creating = _mode.selectedSegmentIndex == 1;
    _invite.hidden = !creating;
    _password.textContentType = creating ? UITextContentTypeNewPassword : UITextContentTypePassword;
    UIButtonConfiguration* button = _submit.configuration;
    button.title = creating ? @"Create account" : @"Sign in";
    _submit.configuration = button;
    _message.hidden = YES;
}

- (void)submit {
    NSString* username = _username.text ?: @"";
    NSString* password = _password.text ?: @"";
    NSString* invite = _invite.text ?: @"";
    if (!username.length || !password.length) {
        _message.text = @"Enter your username and password.";
        _message.hidden = NO;
        return;
    }
    const BOOL creating = _mode.selectedSegmentIndex == 1;
    _password.text = nil;
    _invite.text = nil;
    AciesCommunityResult completion = [self startRequestResuming:NO];
    if (creating) [_client registerUser:username password:password invite:invite completion:completion];
    else [_client signIn:username password:password completion:completion];
}

- (void)continueSaved {
    if (_saved[@"bearer"]) [_client resume:_saved[@"bearer"] completion:[self startRequestResuming:YES]];
}

- (AciesCommunityResult)startRequestResuming:(BOOL)resuming {
    [self.view endEditing:YES];
    _message.hidden = YES;
    [_busy startAnimating];
    for (UIControl* control in @[_continueButton, _mode, _username, _password, _invite, _submit]) {
        control.enabled = NO;
    }
    __weak AciesCommunityForm* weakSelf = self;
    return ^(AciesCommunitySession* session, NSError* error) {
        dispatch_async(dispatch_get_main_queue(), ^{
            AciesCommunityForm* form = weakSelf;
            if (!form) return;
            [form->_busy stopAnimating];
            NSError* failure = error;
            if (session && form->_ready) {
                failure = form->_ready(session);
                if (!failure) {
                    form->_ready = nil;
                    return;
                }
            } else if (resuming && error.code == 401) {
                AciesClearCommunityKeychain(form->_origin);
                form->_saved = nil;
                form->_continueButton.hidden = YES;
            }
            for (UIControl* control in @[form->_continueButton, form->_mode, form->_username,
                                         form->_password, form->_invite, form->_submit]) {
                control.enabled = YES;
            }
            form->_message.text = failure.localizedDescription ?: @"Could not complete the request.";
            form->_message.hidden = NO;
            UIAccessibilityPostNotification(UIAccessibilityAnnouncementNotification, form->_message.text);
        });
    };
}

@end
