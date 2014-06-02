/*
 * Copyright 2013 Mirantis, Inc.
 *
 * Licensed under the Apache License, Version 2.0 (the "License"); you may
 * not use this file except in compliance with the License. You may obtain
 * a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
 * WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
 * License for the specific language governing permissions and limitations
 * under the License.
**/
define(
[
    'utils',
    'models',
    'views/common',
    'views/dialogs',
    'text!templates/cluster/contrail_tab.html',
],
function(utils, models, commonViews, dialogViews, settingsTabTemplate) {
    'use strict';
    var SettingsTab;

    SettingsTab = commonViews.Tab.extend({
        template: _.template(settingsTabTemplate),
        hasChanges: function() {
            return !_.isEqual(this.settings.attributes, this.previousSettings);
        },
        events: {
            'click .btn-apply-changes:not([disabled])': 'applyChanges',
            'click .btn-revert-changes:not([disabled])': 'revertChanges',
            'click .btn-load-defaults:not([disabled])': 'loadDefaults',
            'click .btn-add:not([disabled])': 'addGateway'
        },
        defaultButtonsState: function(buttonState) {
            this.$('.btn:not(.btn-load-defaults)').attr('disabled', buttonState);
            this.$('.btn-load-defaults').attr('disabled', false);
        },
        disableControls: function() {
            this.$('.btn, input, select').attr('disabled', true);
        },
        isLocked: function() {
            return this.model.get('status') != 'new' || !!this.model.task('deploy', 'running');
        },
        checkForChanges: function() {
            this.defaultButtonsState(!this.hasChanges());
        },
        applyChanges: function() {
            this.disableControls();
            return this.model.get('contrail').save({editable: _.cloneDeep(this.settings.attributes)}, {patch: true, wait: true, url: _.result(this.model, 'url') + '/contrail'})
                .done(_.bind(this.setInitialData, this))
                .always(_.bind(function() {
                    this.render();
                    this.model.fetch();
                }, this))
                .fail(_.bind(function() {
                    this.defaultButtonsState(false);
                    utils.showErrorDialog({title: 'OpenStack Settings'});
                }, this));
        },
        revertChanges: function() {
            this.setInitialData();
                ({'editable' : {'wan_gateways' : ['test']}});
            this.render();
        },
        loadDefaults: function() {
            var defaults = new models.Settings();
            this.disableControls();
            defaults.fetch({url: _.result(this.model, 'url') + '/contrail/defaults'}).always(_.bind(function() {
                this.settings = new models.Settings(defaults.get('editable'));
                this.model.get('contrail').set({'editable' : defaults.get('editable')});
                this.render();
                this.checkForChanges();
            }, this));
        },
        setInitialData: function() {
            this.previousSettings = _.cloneDeep(this.model.get('contrail').get('editable'));
            this.settings = new models.ContrailSettings(this.previousSettings);
            this.settings.on('change', _.bind(this.checkForChanges, this));
        },
        composeBindings: function() {
            this.bindings = {};
            _.each(this.settings.attributes, function(settingsGroup, attr) {
                this.bindings['input[name=as_number]'] = 'as_number';
            }, this);
        },
        render: function() {
            this.tearDownRegisteredSubViews();
            this.$el.html(this.template({cluster: this.model, locked: this.isLocked()}));
            if (this.settings) {
                this.composeBindings();
                this.stickit(this.settings);
                this.bindGateways();
            }
            this.$el.i18n();
            return this;
        },
        bindTaskEvents: function(task) {
            return task.get('name') == 'deploy' ? task.on('change:status', this.render, this) : null;
        },
        onNewTask: function(task) {
            return this.bindTaskEvents(task) && this.render();
        },
        initialize: function(options) {
            this.model.on('change:status', this.render, this);
            this.model.get('tasks').each(this.bindTaskEvents, this);
            this.model.get('tasks').on('add', this.onNewTask, this);
            if (!this.model.get('contrail')) {
                this.model.set({'contrail': new models.ContrailSettings()}, {silent: true});
                this.model.get('contrail').deferred = this.model.get('contrail').fetch({url: _.result(this.model, 'url') + '/contrail'});
                this.model.get('contrail').deferred
                    .done(_.bind(function() {
                        this.setInitialData();
                        this.render();
                    }, this));
            } else {
                this.setInitialData();
            }
        },
        addGateway: function() {
            if ($("#add-wan").validationEngine('validate')) {
                var gateways = this.model.get('contrail').get('editable')['wan_gateways'];
                var hostname = this.$('#wan-hostname').val();
                var ip_addr = this.$('#wan-ip').val();
                gateways.push({'hostname' : hostname, 'ip': ip_addr});
                this.model.get('contrail').set({'editable' : {'wan_gateways' : gateways}});
                this.settings.attributes['wan_gateways'] = gateways;
                this.render();
                this.checkForChanges();
                this.$('.btn-add, .btn-delete').attr('disabled', false);
            }
            return false;
        },
        bindGateways: function() {
            var gateways = this.model.get('contrail').get('editable')['wan_gateways'];
            //TODO unbind all bindings
            var _this = this;
            _.each(gateways, function(gateway, index) {
                    var button = _this.$('.btn-delete-' + index);
                    button.off();
                    button.on('click', function() {
                        var i = index;
                        var gateways = _this.model.get('contrail').get('editable')['wan_gateways'];
                        gateways.splice(i, 1);
                        _this.model.get('contrail').set({'editable' : {'wan_gateways' : gateways}});
                        _this.settings.attributes['wan_gateways'] = gateways;
                        _this.render();
                        _this.checkForChanges();
                        _this.$('.btn-add, .btn-delete').attr('disabled', false);
                        return false;
                    });
            })
        }
    });

    return SettingsTab;
});