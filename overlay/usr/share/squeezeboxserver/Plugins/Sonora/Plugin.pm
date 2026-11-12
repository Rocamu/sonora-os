package Plugins::Sonora::Plugin;
use strict;
use warnings;
use base qw(Slim::Plugin::Base);
use JSON::PP;
use Time::HiRes qw(time);
use Slim::Control::Request;
use Slim::Player::Client;
use Slim::Utils::Prefs;
use Slim::Utils::Timers;
my $prefs = preferences('server');
our $guard = 0;
my %lastMode;
sub readJson {
    my ($file) = @_;
    open my $f, '<', $file or return {};
    local $/;my $raw=<$f>;close $f;
    my $obj=eval { decode_json($raw) };
    return ref($obj) eq 'HASH' ? $obj : {};
}
sub initPlugin {
    my $class=shift;$class->SUPER::initPlugin(@_);
    Slim::Control::Request::subscribe(\&connected,[['client'],['new','reconnect']]);
    $prefs->setChange(sub { my ($name,$value,$client)=@_;enforce($client) unless $guard; },'digitalVolumeControl','replayGainMode','transitionType','balance','pitch','bass','treble','preampVolumeControl');
    reconcile();
}
sub ownPlayer {
    my ($client)=@_;return 0 unless $client;
    my $identity=readJson('/etc/sonora/player.json');
    return ($identity->{id}||'') eq $client->id;
}
sub enforce {
    my ($client)=@_;return if $guard || !ownPlayer($client);
    my $cfg=readJson('/etc/sonora/audio.json');my $mode=$cfg->{mode}||'pure';
    local $guard=1;
    my $cp=$prefs->client($client);
    # This appliance connects its local Squeezelite directly to an ALSA device.
    # Declaring digital output permits LMS's native fixed-output control.
    if ($client->can('hasDigitalOut')) { $client->hasDigitalOut(1); }
    if ($mode eq 'pure') {
        my %values=(digitalVolumeControl=>0,replayGainMode=>0,transitionType=>0,balance=>0,pitch=>100,bass=>50,treble=>50,preampVolumeControl=>0);
        for my $key (keys %values) {
            my $old=$cp->get($key);
            $cp->set($key,$values{$key}) if !defined($old)||$old!=$values{$key};
        }
    } elsif ($mode eq 'listening' && ($lastMode{$client->id}||'') ne 'listening') {
        $cp->set('digitalVolumeControl',1);
    }
    $lastMode{$client->id}=$mode;
}
sub connected { my ($request)=@_;enforce($request->client); }
sub reconcile {
    for my $client (Slim::Player::Client::clients()) { enforce($client); }
    Slim::Utils::Timers::setTimer(__PACKAGE__,time()+2,\&reconcile);
}
sub shutdownPlugin {
    Slim::Utils::Timers::killTimers(__PACKAGE__);
    Slim::Control::Request::unsubscribe(\&connected);
}
1;
